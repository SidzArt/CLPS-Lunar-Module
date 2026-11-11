"""Phase 5 CODEX hardware subsystem, protocol, kinematics, LED mapping, and safety tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import codex_rate_limiter
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.integrations.codex.client import MockCodexTransport, get_codex_transport
from app.integrations.codex.protocol import (
    UART_MSG_MOTION_CMD,
    UartFrameError,
    build_codex_command_payload,
    build_signed_headers,
    decode_uno_uart_frame,
    encode_uno_motion_payload,
    encode_uno_uart_frame,
    redact_sensitive_mapping,
    verify_codex_signature,
)
from app.models.admin import Admin, AdminRoleLink, Role
from app.models.catalogue import LandingSite
from app.models.codex import (
    HardwareDevice,
)
from app.models.metrics import ParameterDefinition, SiteMetric
from app.models.simulation import SimulationRun, SimulationSample
from app.services.codex_kinematics import (
    CalibrationRequiredError,
    CalibrationSpec,
    MotionConstraintError,
    compute_kepler_orbital_reference,
    compute_motor_move_plan,
    resolve_physical_duration_seconds,
)
from app.services.codex_template_engine import (
    PlaceholderSpec,
    TemplateRenderError,
    compute_sha256_hex,
    render_firmware_template,
)
from app.services.moon_led_mapping import (
    LedMappingError,
    LedMappingVerificationError,
    LedPixelOutput,
    LedRegionDefinition,
    resolve_site_to_moon_led_region,
    validate_region_index,
)


def _create_role_auth_headers(client: TestClient, username: str, role_key: str) -> dict[str, str]:
    """Create or reuse test admin user bound to a specific RBAC role and log in."""
    db: Session = SessionLocal()
    try:
        admin = db.scalar(select(Admin).where(Admin.username == username))
        if admin is None:
            admin = Admin(
                username=username,
                password_hash=hash_password("CodexRolePass123!"),
                display_name=username,
                is_active=True,
            )
            db.add(admin)
            db.flush()
            role = db.scalar(select(Role).where(Role.role_key == role_key))
            assert role is not None, f"Seeded role '{role_key}' missing"
            db.add(AdminRoleLink(admin_id=admin.admin_id, role_id=role.role_id))
            db.commit()
    finally:
        db.close()

    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "CodexRolePass123!"},
    )
    assert resp.status_code == 200, resp.text
    client.cookies.clear()
    return {"Authorization": f"Bearer {resp.json()['session_token']}"}


def _seed_completed_simulation(site_code: str = "LUNA-MOUTON-01") -> tuple[int, uuid.UUID]:
    """Ensure a deterministic completed simulation run with sun/earth vectors exists for site."""
    db: Session = SessionLocal()
    try:
        site = db.scalar(select(LandingSite).where(LandingSite.site_code == site_code))
        assert site is not None, f"Published site '{site_code}' not found"
        sim = SimulationRun(
            simulation_id=uuid.uuid4(),
            site_id=site.site_id,
            start_time_utc=datetime(2026, 4, 9, 11, 5, 0, tzinfo=UTC),
            end_time_utc=datetime(2026, 4, 19, 11, 5, 0, tzinfo=UTC),
            duration_seconds=864000,
            playback_speed=86400.0,
            sample_interval_seconds=900,
            ephemeris_source="NAIF_DE440",
            ephemeris_version="de440s.bsp",
            coordinate_frame="MOON_ME",
            aberration_policy="LT+S",
            algorithm_version="v1.0",
            quality_state="verified_terrain_aware",
            status="completed",
            progress_pct=100.0,
        )
        db.add(sim)
        db.flush()
        sample = SimulationSample(
            simulation_id=sim.simulation_id,
            sample_index=0,
            timestamp_utc=sim.start_time_utc,
            ephemeris_time=829004769.18,
            sun_azimuth_deg=122.4,
            sun_elevation_deg=14.8,
            sun_range_km=150000000.0,
            earth_azimuth_deg=358.1,
            earth_elevation_deg=6.2,
            earth_range_km=384400.0,
            sun_horizon_deg=1.5,
            earth_horizon_deg=1.2,
            sun_visibility_status="VISIBLE",
            earth_visibility_status="VISIBLE",
            concurrent_visible=True,
            sun_dir_moon_x=0.819152,
            sun_dir_moon_y=0.573576,
            sun_dir_moon_z=0.0,
            earth_dir_moon_x=0.9986,
            earth_dir_moon_y=0.0523,
            earth_dir_moon_z=0.0,
            quality_status="verified_terrain_aware",
        )
        db.add(sample)
        db.commit()
        return site.site_id, sim.simulation_id
    finally:
        db.close()


def _configure_verified_bench(
    client: TestClient, admin_headers: dict[str, str], mock_transport: MockCodexTransport
) -> dict[str, Any]:
    """Put all 3 CODEX mock devices, configs, calibrations, and region 13 LEDs into ready state."""
    for ck, board, fw_target, expected_fw in (
        ("wifi_bridge", "ESP32", "esp32:esp32:esp32", "codex-bridge-v1.0.0"),
        ("motion_uno", "Arduino Uno R3", "arduino:avr:uno", "codex-uno-v1.0.0"),
        ("moon_led_s3", "ESP32-S3", "esp32:esp32:esp32s3", "codex-s3-v1.0.0"),
    ):
        cfg_resp = client.put(
            f"/api/v1/admin/codex/configurations/{ck}",
            headers=admin_headers,
            json={"board_model": board, "firmware_target": fw_target},
        )
        assert cfg_resp.status_code == 200, cfg_resp.text

        mock_transport.configure_device(
            ck,
            offline=False,
            timeout=False,
            firmware_version=expected_fw,
            uart_ok=(ck in ("wifi_bridge", "motion_uno")),
            driver_config_ok=(ck == "motion_uno"),
            led_controller_ok=(ck == "moon_led_s3"),
            estop_latched=False,
        )
        hb_resp = client.post(
            f"/api/v1/admin/codex/devices/{ck}/heartbeat",
            headers=admin_headers,
            json={
                "probe_via_transport": True,
                "expected_firmware_version": expected_fw,
                "verification_status": "bench_verified",
                "reset_estop_latch": True,
            },
        )
        assert hb_resp.status_code == 200, hb_resp.text

    nema_resp = client.post(
        "/api/v1/admin/codex/calibrations",
        headers=admin_headers,
        json={
            "controller_key": "motion_uno",
            "motor_key": "nema17",
            "motor_name": "NEMA17 Elliptical Arm Drive",
            "motor_model": "17HS4401",
            "driver_model": "A4988",
            "gear_reduction_ratio": 2.0,
            "full_steps_per_rev": 200,
            "microsteps": 8,
            "direction_sign": 1,
            "max_step_rate": 2000,
            "acceleration": 600,
            "backlash_steps": 4,
            "zero_offset_deg": 0.0,
            "travel_min_deg": 0.0,
            "travel_max_deg": 360.0,
            "calibration_version": "nema-v2.0-verified",
            "measured_by": "Bench Test Harness",
            "verification_status": "bench_verified",
        },
    )
    assert nema_resp.status_code == 201, nema_resp.text

    byj_resp = client.post(
        "/api/v1/admin/codex/calibrations",
        headers=admin_headers,
        json={
            "controller_key": "motion_uno",
            "motor_key": "byj",
            "motor_name": "BYJ Earth Frame Drive",
            "motor_model": "28BYJ-48",
            "driver_model": "ULN2003",
            "gear_reduction_ratio": 64.0,
            "full_steps_per_rev": 32,
            "microsteps": 1,
            "direction_sign": -1,
            "max_step_rate": 800,
            "acceleration": 400,
            "backlash_steps": 2,
            "zero_offset_deg": 0.0,
            "travel_min_deg": 0.0,
            "travel_max_deg": 360.0,
            "calibration_version": "byj-v2.0-verified",
            "measured_by": "Bench Test Harness",
            "verification_status": "bench_verified",
        },
    )
    assert byj_resp.status_code == 201, byj_resp.text

    # Region 13 covering Mons Mouton (-84.65 deg, +31.02 deg)
    led_resp = client.post(
        "/api/v1/admin/codex/led-mapping",
        headers=admin_headers,
        json={
            "region_index": 13,
            "region_name": "South Polar Artemis Ridge",
            "centroid_lat": -85.0,
            "centroid_lon": 30.0,
            "boundary_polygon": [
                {"lat": -89.0, "lon": -20.0},
                {"lat": -89.0, "lon": 80.0},
                {"lat": -80.0, "lon": 80.0},
                {"lat": -80.0, "lon": -20.0},
            ],
            "pixel_indices": [24, 25],
            "mapping_version": "v2.0-verified",
            "verification_status": "bench_verified",
            "topology_mode": "addressable_strip",
        },
    )
    assert led_resp.status_code == 200, led_resp.text
    return {
        "nema_cal_id": nema_resp.json()["calibration_id"],
        "byj_cal_id": byj_resp.json()["calibration_id"],
    }


@pytest.fixture(autouse=True)
def _reset_codex_test_state() -> Any:
    """Reset mock transport and rate limiters between CODEX tests cleanly."""
    codex_rate_limiter.reset()
    transport = get_codex_transport("mock")
    assert isinstance(transport, MockCodexTransport)
    transport.reset()
    yield
    transport.reset()
    codex_rate_limiter.reset()


# ==============================================================================
# 1. UNIT TESTS: KINEMATICS, LED MAPPING, TEMPLATE ENGINE, HMAC, UART FRAMING
# ==============================================================================


def test_kinematics_step_conversion_direction_limits_and_kepler() -> None:
    """Verify Kepler period separation, exact step conversion, direction_sign, backlash, & limits."""
    kepler = compute_kepler_orbital_reference(864000)  # 10 Earth days
    assert 27.0 < kepler["kepler_ideal_period_days"] < 28.0
    assert resolve_physical_duration_seconds(864000, 86400.0) == 10

    spec = CalibrationSpec(
        motor_key="nema17",
        controller_key="motion_uno",
        motor_name="NEMA17 Test",
        calibration_version="v1-bench",
        verification_status="bench_verified",
        gear_reduction_ratio=2.0,
        full_steps_per_rev=200,
        microsteps=8,
        direction_sign=-1,
        max_step_rate=2000,
        acceleration=500,
        backlash_steps=5,
        zero_offset_deg=0.0,
        travel_min_deg=0.0,
        travel_max_deg=180.0,
    )
    # 90 deg = 0.25 rev * (200 * 8 * 2.0 = 3200 steps/rev) = 800 steps + 5 backlash = 805
    plan = compute_motor_move_plan(
        spec,
        target_angle_deg=90.0,
        current_angle_deg=0.0,
        permitted_move_seconds=10.0,
        require_verified=True,
    )
    assert plan.base_steps == 800
    assert plan.backlash_compensation_steps == 5
    assert plan.total_steps == 805
    assert plan.hardware_direction == -1  # positive delta * direction_sign(-1)
    assert plan.profile_shape == "triangular"
    assert plan.step_interval_us > 0

    # Travel limit violation rejected unless clamp enabled
    with pytest.raises(MotionConstraintError) as err:
        compute_motor_move_plan(
            spec, target_angle_deg=210.0, permitted_move_seconds=10.0, require_verified=True
        )
    assert err.value.code == "travel_limit_violation"

    # Clamped move hits exact 180.0 deg
    clamped = compute_motor_move_plan(
        spec,
        target_angle_deg=210.0,
        permitted_move_seconds=10.0,
        require_verified=True,
        clamp_to_travel_limits=True,
    )
    assert clamped.clamped_to_limits is True
    assert clamped.target_angle_deg == 180.0

    # Impossible speed exceeds acceleration envelope
    with pytest.raises(MotionConstraintError) as speed_err:
        compute_motor_move_plan(
            spec, target_angle_deg=180.0, permitted_move_seconds=0.1, require_verified=True
        )
    assert speed_err.value.code == "acceleration_time_exceeded"

    # Unverified calibration blocked in strict mode
    unver = CalibrationSpec(**{**spec.__dict__, "verification_status": "unverified"})
    with pytest.raises(CalibrationRequiredError):
        compute_motor_move_plan(
            unver, target_angle_deg=45.0, permitted_move_seconds=5.0, require_verified=True
        )


def test_moon_led_13_region_polygon_boundary_tiebreak_and_centroid_fallback() -> None:
    """Verify spherical polygon resolution, lowest-index boundary tie-break, & unverified gates."""
    with pytest.raises(LedMappingError):
        validate_region_index(0)
    with pytest.raises(LedMappingError):
        validate_region_index(14)

    r1 = LedRegionDefinition(
        region_index=1,
        region_name="Region One",
        mapping_version="v1",
        verification_status="bench_verified",
        centroid_lat_deg=5.0,
        centroid_lon_deg=-5.0,
        boundary_polygon=[[-10, 0], [0, 0], [0, 10], [-10, 10]],
        pixel_indices=[0, 1],
        normalized_pixels=[LedPixelOutput(0, 0, 0, "addressable_strip", "bench_verified")],
    )
    r2 = LedRegionDefinition(
        region_index=2,
        region_name="Region Two",
        mapping_version="v1",
        verification_status="bench_verified",
        centroid_lat_deg=5.0,
        centroid_lon_deg=5.0,
        boundary_polygon=[[0, 0], [10, 0], [10, 10], [0, 10]],
        pixel_indices=[2, 3],
        normalized_pixels=[LedPixelOutput(2, 0, 0, "addressable_strip", "bench_verified")],
    )

    # Exact shared boundary lon=0.0, lat=5.0 must break deterministically to region_index=1
    tie_res = resolve_site_to_moon_led_region(
        site_lat_deg=5.0,
        site_lon_deg=0.0,
        regions=[r2, r1],
        require_verified_mapping=True,
    )
    assert tie_res.region_index == 1
    assert tie_res.boundary_tie_broken is True
    assert tie_res.mapping_mode == "polygon_boundary_tie_broken"
    assert tie_res.is_verified_for_hardware is True

    # Point outside both polygons -> centroid fallback disallowed in strict mode
    with pytest.raises(LedMappingVerificationError):
        resolve_site_to_moon_led_region(
            site_lat_deg=-40.0,
            site_lon_deg=40.0,
            regions=[r1, r2],
            require_verified_mapping=True,
            allow_centroid_fallback=False,
        )

    # Approximate centroid fallback allowed explicitly in preview and marked approximate
    approx = resolve_site_to_moon_led_region(
        site_lat_deg=4.0,
        site_lon_deg=40.0,
        regions=[r1, r2],
        require_verified_mapping=False,
        allow_centroid_fallback=True,
    )
    assert approx.mapping_mode == "approximate_centroid_only"
    assert approx.region_index == 2
    assert approx.is_verified_for_hardware is False


def test_strict_firmware_template_engine_allowlist_and_injection_blocks() -> None:
    """Verify strict {{PLACEHOLDER}} rendering, bounds checks, and C/C++ injection rejection."""
    src = "#define MAX_STEPS {{MAX_STEPS}}\n#define TAG {{TAG}}\n#define ENABLED {{ENABLED}}\n"
    checksum = compute_sha256_hex(src)
    specs = [
        PlaceholderSpec("MAX_STEPS", "int", validation_schema={"min": 100, "max": 50000}),
        PlaceholderSpec(
            "TAG", "string", injection_format="c_string", validation_schema={"max_length": 20}
        ),
        PlaceholderSpec("ENABLED", "bool", injection_format="int_flag"),
    ]
    res = render_firmware_template(
        src,
        specs,
        {"MAX_STEPS": 1600, "TAG": "LUNAR_NORTH", "ENABLED": True},
        expected_source_checksum=checksum,
    )
    assert "#define MAX_STEPS 1600" in res.rendered_source
    assert '#define TAG "LUNAR_NORTH"' in res.rendered_source
    assert "#define ENABLED 1" in res.rendered_source

    # Reject undeclared placeholder
    with pytest.raises(TemplateRenderError) as err1:
        render_firmware_template("int x = {{SNEAKY_VAR}};", specs, {})
    assert err1.value.code == "undeclared_placeholder"

    # Reject C injection payload
    with pytest.raises(TemplateRenderError) as err2:
        render_firmware_template(
            src, specs, {"MAX_STEPS": 1000, "TAG": 'foo";system();//', "ENABLED": False}
        )
    assert err2.value.code == "unsafe_placeholder_characters"

    # Reject out of bounds
    with pytest.raises(TemplateRenderError) as err3:
        render_firmware_template(src, specs, {"MAX_STEPS": 999999, "TAG": "OK", "ENABLED": True})
    assert err3.value.code == "placeholder_out_of_bounds"


def test_codex_protocol_hmac_redaction_and_uno_uart_crc16() -> None:
    """Verify Protocol v1 HMAC signing/tamper check, log redaction, & UART CRC16 corruption check."""
    payload = build_codex_command_payload(
        command_id=str(uuid.uuid4()),
        simulation_id=str(uuid.uuid4()),
        site_id=136,
        sequence_number=7,
        ttl_seconds=300,
        device_targets=["wifi_bridge", "motion_uno", "moon_led_s3"],
        configuration_version="cfg-1",
        calibration_version="cal-1",
        led_mapping_version="v2.0",
        motor_commands={
            "permitted_move_seconds": 10,
            "nema17": {"total_steps": 400},
            "byj": {"total_steps": 120},
        },
        moon_led={"region_index": 13, "pixel_indices": [24, 25]},
    )
    headers = build_signed_headers("unit-test-shared-secret-key", payload)
    assert verify_codex_signature(
        "unit-test-shared-secret-key",
        provided_signature=headers["X-Codex-Signature"],
        command_id=payload["command_id"],
        issued_at_utc=payload["issued_at_utc"],
        nonce=payload["nonce"],
        sequence_number=payload["sequence_number"],
        payload=payload,
    )

    # Tampered sequence invalidates HMAC
    assert not verify_codex_signature(
        "unit-test-shared-secret-key",
        provided_signature=headers["X-Codex-Signature"],
        command_id=payload["command_id"],
        issued_at_utc=payload["issued_at_utc"],
        nonce=payload["nonce"],
        sequence_number=8,
        payload=payload,
    )

    # Redaction hides signature and secret values
    redacted = redact_sensitive_mapping({**headers, "codex_shared_secret": "top-secret"})
    assert redacted["X-Codex-Signature"] == "[REDACTED]"
    assert redacted["codex_shared_secret"] == "[REDACTED]"

    # Binary Uno UART encode/decode round-trip and CRC corruption rejection
    compact = encode_uno_motion_payload(
        nema17_plan={"hardware_direction": 1, "total_steps": 800, "step_interval_us": 12500},
        byj_plan={"hardware_direction": -1, "total_steps": 512, "step_interval_us": 19531},
        physical_duration_seconds=10,
    )
    frame = encode_uno_uart_frame(UART_MSG_MOTION_CMD, 7, compact)
    decoded = decode_uno_uart_frame(frame)
    assert decoded.msg_type == UART_MSG_MOTION_CMD
    assert decoded.sequence_number == 7
    assert decoded.payload == compact

    corrupted = bytearray(frame)
    corrupted[-3] ^= 0xFF
    with pytest.raises(UartFrameError) as uerr:
        decode_uno_uart_frame(bytes(corrupted))
    assert uerr.value.code == "crc_mismatch"


# ==============================================================================
# 2. INTEGRATION TESTS: FASTAPI, POSTGRESQL FSM, RBAC, PREPARE/EXECUTE/ESTOP
# ==============================================================================


def test_codex_public_status_and_rbac_enforcement(
    client: TestClient,
    admin_auth_headers: dict[str, str],
    viewer_auth_headers: dict[str, str],
) -> None:
    """Verify public sanitized status, unauth/viewer blocks, operator vs admin RBAC split."""
    # Public status works unauthenticated and exposes no raw endpoint_host or secrets
    pub = client.get("/api/v1/codex/status")
    assert pub.status_code == 200
    data = pub.json()
    assert len(data["controllers"]) == 3
    for ctrl in data["controllers"]:
        assert "endpoint_host" not in ctrl
        assert "reported_firmware_checksum" not in ctrl
        assert ctrl["battery_voltage_available"] is False
        assert ctrl["battery_voltage_v"] is None

    # Viewer & unauthenticated callers rejected from operator & admin hardware routes
    op_headers = _create_role_auth_headers(client, "test_hw_operator", "hardware_operator")
    hw_admin_headers = _create_role_auth_headers(client, "test_hw_admin", "hardware_admin")
    client.cookies.clear()

    assert client.post("/api/v1/codex/estop", json={"reason": "test"}).status_code == 401
    assert (
        client.post(
            "/api/v1/codex/estop", headers=viewer_auth_headers, json={"reason": "viewer stop"}
        ).status_code
        == 403
    )
    assert client.get("/api/v1/admin/codex/devices", headers=op_headers).status_code == 403
    assert client.get("/api/v1/admin/codex/devices", headers=viewer_auth_headers).status_code == 403
    assert client.get("/api/v1/admin/codex/devices", headers=hw_admin_headers).status_code == 200


def test_codex_prepare_vs_execute_full_verified_flow_and_idempotency(
    client: TestClient, admin_auth_headers: dict[str, str]
) -> None:
    """Verify full verified mock flow, prepare zero-actuation, confirmation gate, & idempotency."""
    mock_transport = get_codex_transport("mock")
    assert isinstance(mock_transport, MockCodexTransport)
    _site_id, sim_id = _seed_completed_simulation()
    op_headers = _create_role_auth_headers(client, "test_hw_operator", "hardware_operator")

    # 1. On default offline/unverified bench, prepare succeeds cleanly with zero actuation & blockers
    prep_unver = client.post(
        "/api/v1/codex/runs/prepare",
        headers=op_headers,
        json={"simulation_id": str(sim_id), "execution_mode": "full_codex"},
    )
    assert prep_unver.status_code == 200, prep_unver.text
    pu = prep_unver.json()
    assert pu["actuation_performed"] is False
    assert pu["ready_to_execute"] is False
    assert pu["preflight_total_steps"] == 16
    assert len(mock_transport.dispatched_commands) == 0

    # 2. Configure full verified bench via admin endpoints
    _configure_verified_bench(client, admin_auth_headers, mock_transport)

    prep_ok = client.post(
        "/api/v1/codex/runs/prepare",
        headers=op_headers,
        json={
            "simulation_id": str(sim_id),
            "execution_mode": "full_codex",
            "physical_duration_seconds": 15,
        },
    )
    assert prep_ok.status_code == 200, prep_ok.text
    po = prep_ok.json()
    assert po["ready_to_execute"] is True, f"Prepare blockers: {po['blockers']}"
    assert po["preflight_passed_count"] == 16
    assert po["actuation_performed"] is False
    assert len(mock_transport.dispatched_commands) == 0
    assert po["moon_led_plan"]["region_index"] == 13
    run_id = po["hardware_run_id"]

    # 3. Attempting execute without confirmed=True returns 400
    bad_confirm = client.post(
        "/api/v1/codex/runs",
        headers=op_headers,
        json={"hardware_run_id": run_id, "confirmed": False, "idempotency_key": "idem-bad-1"},
    )
    assert bad_confirm.status_code == 400

    # 4. Execute with confirmed=True dispatches signed commands + UART frame cleanly
    idem_key = f"idem-exec-{uuid.uuid4()}"
    exec_resp = client.post(
        "/api/v1/codex/runs",
        headers=op_headers,
        json={"hardware_run_id": run_id, "confirmed": True, "idempotency_key": idem_key},
    )
    assert exec_resp.status_code == 201, exec_resp.text
    ex = exec_resp.json()
    assert ex["status"] == "completed"
    assert len(ex["acknowledgements"]) == 2
    assert len(mock_transport.dispatched_commands) == 2
    # Signature never leaked in logs or response
    assert "X-Codex-Signature" not in ex["prepared_payload"]
    # Bridge received encoded binary UART frame
    bridge_cmd = next(
        c for c in mock_transport.dispatched_commands if c["controller_key"] == "wifi_bridge"
    )
    assert bridge_cmd["uart_frame_len"] > 12
    assert bridge_cmd["headers"]["X-Codex-Signature"] == "[REDACTED]"

    # 5. Re-submitting same idempotency_key returns existing run without re-dispatching
    dup_resp = client.post(
        "/api/v1/codex/runs",
        headers=op_headers,
        json={"hardware_run_id": run_id, "confirmed": True, "idempotency_key": idem_key},
    )
    assert dup_resp.status_code == 201
    assert dup_resp.json()["command_id"] == ex["command_id"]
    assert len(mock_transport.dispatched_commands) == 2

    # 6. Events endpoint lists RUN_PREPARED & RUN_COMPLETED
    ev_resp = client.get(f"/api/v1/codex/runs/{run_id}/events", headers=op_headers)
    assert ev_resp.status_code == 200
    ev_types = [e["event_type"] for e in ev_resp.json()["events"]]
    assert "RUN_PREPARED" in ev_types
    assert "RUN_COMPLETED" in ev_types


def test_codex_fault_detection_stale_heartbeat_led_only_and_estop(
    client: TestClient, admin_auth_headers: dict[str, str]
) -> None:
    """Verify firmware mismatch, stale heartbeat, UART failure, led_only mode, and E-STOP latch."""
    mock_transport = get_codex_transport("mock")
    assert isinstance(mock_transport, MockCodexTransport)
    _, sim_id = _seed_completed_simulation()
    _configure_verified_bench(client, admin_auth_headers, mock_transport)
    op_headers = _create_role_auth_headers(client, "test_hw_operator", "hardware_operator")

    # 1. Firmware mismatch blocks execution cleanly
    mock_transport.configure_device("wifi_bridge", firmware_version="codex-bridge-WRONG")
    client.post(
        "/api/v1/admin/codex/devices/wifi_bridge/heartbeat",
        headers=admin_auth_headers,
        json={"probe_via_transport": True},
    )
    pub = client.get("/api/v1/codex/status").json()
    bridge_state = next(c for c in pub["controllers"] if c["controller_key"] == "wifi_bridge")
    assert bridge_state["health_state"] == "firmware_mismatch"

    # 2. Degraded led_only executes smoothly even when bridge/Uno have firmware mismatch or are offline!
    prep_led = client.post(
        "/api/v1/codex/runs/prepare",
        headers=op_headers,
        json={"simulation_id": str(sim_id), "execution_mode": "led_only"},
    )
    assert prep_led.status_code == 200
    assert prep_led.json()["ready_to_execute"] is True, (
        f"LED-only blockers: {prep_led.json()['blockers']}"
    )
    exec_led = client.post(
        "/api/v1/codex/runs",
        headers=op_headers,
        json={
            "hardware_run_id": prep_led.json()["hardware_run_id"],
            "confirmed": True,
            "idempotency_key": f"idem-led-{uuid.uuid4()}",
        },
    )
    assert exec_led.status_code == 201
    assert exec_led.json()["status"] == "completed"
    assert [a["controller_key"] for a in exec_led.json()["acknowledgements"]] == ["moon_led_s3"]

    # 3. Restore bridge, simulate UART failure during execute -> marks run partial_fault & device fault
    mock_transport.configure_device("wifi_bridge", firmware_version="codex-bridge-v1.0.0")
    client.post(
        "/api/v1/admin/codex/devices/wifi_bridge/heartbeat",
        headers=admin_auth_headers,
        json={"probe_via_transport": True},
    )
    prep_full = client.post(
        "/api/v1/codex/runs/prepare",
        headers=op_headers,
        json={"simulation_id": str(sim_id), "execution_mode": "full_codex"},
    )
    assert prep_full.json()["ready_to_execute"] is True
    mock_transport.configure_device("wifi_bridge", uart_failure=True)
    fault_exec = client.post(
        "/api/v1/codex/runs",
        headers=op_headers,
        json={
            "hardware_run_id": prep_full.json()["hardware_run_id"],
            "confirmed": True,
            "idempotency_key": f"idem-uart-fail-{uuid.uuid4()}",
        },
    )
    assert fault_exec.status_code == 201
    assert fault_exec.json()["status"] == "partial_fault"

    # 4. E-STOP interrupts, dispatches ESTOP UART frame, latches devices, and blocks new execute
    estop_resp = client.post(
        "/api/v1/codex/estop",
        headers=op_headers,
        json={"reason": "Mechanical interference check"},
    )
    assert estop_resp.status_code == 200
    assert estop_resp.json()["estop_latched"] is True

    prep_blocked = client.post(
        "/api/v1/codex/runs/prepare",
        headers=op_headers,
        json={"simulation_id": str(sim_id), "execution_mode": "led_only"},
    )
    assert prep_blocked.json()["ready_to_execute"] is False
    exec_blocked = client.post(
        "/api/v1/codex/runs",
        headers=op_headers,
        json={
            "hardware_run_id": prep_blocked.json()["hardware_run_id"],
            "confirmed": True,
            "idempotency_key": f"idem-estop-{uuid.uuid4()}",
        },
    )
    assert exec_blocked.status_code == 409

    # 5. Stale heartbeat automatically marks device offline
    db: Session = SessionLocal()
    try:
        s3 = db.scalar(select(HardwareDevice).where(HardwareDevice.controller_key == "moon_led_s3"))
        assert s3 is not None
        s3.estop_latched = False
        s3.last_heartbeat_at = datetime.now(UTC) - timedelta(
            seconds=settings.CODEX_HEARTBEAT_STALE_SECONDS + 15
        )
        db.commit()
    finally:
        db.close()
    stale_pub = client.get("/api/v1/codex/status").json()
    s3_state = next(c for c in stale_pub["controllers"] if c["controller_key"] == "moon_led_s3")
    assert s3_state["health_state"] == "offline"
    assert s3_state["heartbeat_fresh"] is False


def test_admin_code_versions_and_versioned_calibrations(
    client: TestClient, admin_auth_headers: dict[str, str]
) -> None:
    """Verify calibration history preservation and admin firmware code template preview."""
    c1 = client.post(
        "/api/v1/admin/codex/calibrations",
        headers=admin_auth_headers,
        json={
            "controller_key": "motion_uno",
            "motor_key": "nema17",
            "motor_name": "NEMA17 Axis",
            "gear_reduction_ratio": 1.5,
            "full_steps_per_rev": 200,
            "microsteps": 8,
            "direction_sign": 1,
            "max_step_rate": 1500,
            "acceleration": 400,
            "calibration_version": "hist-v1",
            "verification_status": "bench_verified",
            "measured_by": "Engineer A",
        },
    )
    assert c1.status_code == 201
    c2 = client.post(
        "/api/v1/admin/codex/calibrations",
        headers=admin_auth_headers,
        json={
            "controller_key": "motion_uno",
            "motor_key": "nema17",
            "motor_name": "NEMA17 Axis",
            "gear_reduction_ratio": 2.0,
            "full_steps_per_rev": 200,
            "microsteps": 8,
            "direction_sign": 1,
            "max_step_rate": 1800,
            "acceleration": 500,
            "calibration_version": "hist-v2",
            "verification_status": "unverified",
        },
    )
    assert c2.status_code == 201
    assert c2.json()["supersedes_calibration_id"] == c1.json()["calibration_id"]

    # Firmware code version create + allow-listed render preview
    cv_resp = client.post(
        "/api/v1/admin/hardware/code-versions",
        headers=admin_auth_headers,
        json={
            "controller_key": "motion_uno",
            "version_label": "uno-phase5-tpl-v1",
            "board_target": "arduino:avr:uno",
            "source_code": "#define NEMA_STEPS {{NEMA_STEPS}}\n#define STEP_US {{STEP_US}}\n",
            "placeholders": [
                {
                    "placeholder_key": "NEMA_STEPS",
                    "description": "NEMA step count",
                    "data_type": "int",
                    "validation_schema": {"min": 0, "max": 20000},
                },
                {
                    "placeholder_key": "STEP_US",
                    "description": "Step interval microseconds",
                    "data_type": "int",
                    "validation_schema": {"min": 100, "max": 1000000},
                },
            ],
        },
    )
    assert cv_resp.status_code == 201, cv_resp.text
    cv_id = cv_resp.json()["code_version_id"]

    prev_resp = client.post(
        f"/api/v1/admin/hardware/code-versions/{cv_id}/render-preview",
        headers=admin_auth_headers,
        json={"values": {"NEMA_STEPS": 800, "STEP_US": 5000}},
    )
    assert prev_resp.status_code == 200
    assert "#define NEMA_STEPS 800" in prev_resp.json()["rendered_source"]


def test_cross_phase_audit_remediation_regressions(client: TestClient) -> None:
    """Confirm Step 1 DB hygiene, published-site gating, and 004 metric seeding."""
    db: Session = SessionLocal()
    try:
        # 1. No unsourced site_metrics on real candidate sites falsely labeled verified
        bad_metrics = db.scalars(
            select(SiteMetric)
            .join(LandingSite, LandingSite.site_id == SiteMetric.site_id)
            .where(
                LandingSite.site_code != "CLPS-TEST-001",
                SiteMetric.source_id.is_(None),
                SiteMetric.data_quality_status == "verified",
            )
        ).all()
        assert len(bad_metrics) == 0

        # 2. illumination_annual_avg exists cleanly from 004 fix
        illum = db.scalar(
            select(ParameterDefinition).where(
                ParameterDefinition.parameter_key == "illumination_annual_avg"
            )
        )
        assert illum is not None

        # 3. Create an ephemeral archived site and verify all public/sim endpoints block it
        archived_site = LandingSite(
            site_code="ARC-AUDIT-999",
            site_slug="arc-audit-999",
            site_name="Archived Audit Site",
            latitude_deg=-84.0,
            longitude_deg=12.0,
            catalogue_status="archived",
        )
        db.add(archived_site)
        db.commit()
        db.refresh(archived_site)
        archived_id = archived_site.site_id
    finally:
        db.close()

    try:
        sites_resp = client.get("/api/v1/sites?limit=100")
        assert sites_resp.status_code == 200
        codes = [s["site_code"] for s in sites_resp.json()["items"]]
        assert "ARC-AUDIT-999" not in codes
        assert client.get("/api/v1/sites/arc-audit-999").status_code == 404

        sim_resp = client.post(
            "/api/v1/simulations",
            json={
                "site_id": archived_id,
                "start_time": "2026-04-09T11:05:00Z",
                "duration_seconds": 3600,
                "playback_speed": 1.0,
            },
        )
        assert sim_resp.status_code == 404
    finally:
        cleanup_db: Session = SessionLocal()
        try:
            row = cleanup_db.get(LandingSite, archived_id)
            if row is not None:
                cleanup_db.delete(row)
                cleanup_db.commit()
        finally:
            cleanup_db.close()


def test_firmware_static_safety_guards_and_protocol_parity(
    client: TestClient,
    admin_auth_headers: dict[str, str],
) -> None:
    """Phase 5 close-out: verify firmware sketches keep #error blocks and match codex.v1 protocol."""
    from pathlib import Path

    from app.integrations.codex.protocol import (
        UART_MSG_ACK,
        UART_MSG_ESTOP,
        UART_MSG_MOTION_CMD,
        UART_SOF,
    )
    from app.models.codex import HardwareCodeVersion

    repo_root = Path(__file__).resolve().parents[2]
    firmware_dir = repo_root / "firmware"
    assert (firmware_dir / "arduino-uno-motion" / "config.example.h").exists()
    assert (firmware_dir / "esp32-s3-moon-led" / "secrets.example.h").exists()
    assert (firmware_dir / "esp32-wifi-bridge" / "secrets.example.h").exists()
    assert not (firmware_dir / "arduino-uno-motion" / "config.h").exists()
    assert not (firmware_dir / "esp32-s3-moon-led" / "config.h").exists()
    assert not (firmware_dir / "esp32-wifi-bridge" / "secrets.h").exists()

    uno_ino = (firmware_dir / "arduino-uno-motion" / "arduino-uno-motion.ino").read_text()
    s3_ino = (firmware_dir / "esp32-s3-moon-led" / "esp32-s3-moon-led.ino").read_text()
    wifi_ino = (firmware_dir / "esp32-wifi-bridge" / "esp32-wifi-bridge.ino").read_text()

    assert '#error "SAFETY BLOCK:' in uno_ino
    assert '#error "SAFETY BLOCK:' in s3_ino
    assert "X-Codex-Signature" in wifi_ino
    assert f"0x{UART_SOF:04X}" in uno_ino
    assert f"0x{UART_SOF:04X}" in wifi_ino
    assert f"0x{UART_MSG_MOTION_CMD:02X}" in uno_ino
    assert f"0x{UART_MSG_ESTOP:02X}" in uno_ino
    assert f"0x{UART_MSG_ACK:02X}" in uno_ino

    # Create valid code version & validate syntax statically (never auto-flashes)
    cv_resp = client.post(
        "/api/v1/admin/hardware/code-versions",
        headers=admin_auth_headers,
        json={
            "controller_key": "motion_uno",
            "version_label": "v-static-closeout-1",
            "source_code": uno_ino,
            "language": "cpp",
            "board_target": "arduino:avr:uno",
            "placeholders": [],
            "activate": False,
        },
    )
    assert cv_resp.status_code == 201
    cv_id = cv_resp.json()["code_version_id"]

    val_resp = client.post(
        f"/api/v1/admin/hardware/code-versions/{cv_id}/validate-syntax",
        headers=admin_auth_headers,
    )
    assert val_resp.status_code == 200
    val_data = val_resp.json()
    assert val_data["valid_static_checks"] is True
    assert val_data["undeclared_tokens"] == []
    assert any("SAFETY BLOCK" in w for w in val_data["warnings"])

    # Clean up temporary immutable row if possible
    cleanup_db: Session = SessionLocal()
    try:
        row = cleanup_db.get(HardwareCodeVersion, cv_id)
        if row is not None:
            cleanup_db.delete(row)
            cleanup_db.commit()
    finally:
        cleanup_db.close()


def test_codex_fault_injection_and_recovery(
    client: TestClient,
    admin_auth_headers: dict[str, str],
) -> None:
    """Phase 5 close-out: simulate controller fault + E-STOP latch and verify controlled recovery."""
    # Inject fault & E-STOP on motion_uno
    fault_resp = client.post(
        "/api/v1/admin/codex/devices/motion_uno/heartbeat",
        headers=admin_auth_headers,
        json={
            "probe_via_transport": False,
            "estop_latched": True,
            "last_error_code": "SIMULATED_OVERCURRENT",
            "last_error_message": "Simulated bench limit fault injection",
        },
    )
    assert fault_resp.status_code == 200
    uno = next(d for d in fault_resp.json()["devices"] if d["controller_key"] == "motion_uno")
    assert uno["estop_latched"] is True
    assert uno["last_error_code"] == "SIMULATED_OVERCURRENT"

    # Reset fault and release E-STOP latch via explicit heartbeat recovery
    recover_resp = client.post(
        "/api/v1/admin/codex/devices/motion_uno/heartbeat",
        headers=admin_auth_headers,
        json={
            "probe_via_transport": False,
            "estop_latched": False,
            "reset_estop_latch": True,
            "uart_ok": True,
            "driver_config_ok": True,
        },
    )
    assert recover_resp.status_code == 200
    recovered = next(
        d for d in recover_resp.json()["devices"] if d["controller_key"] == "motion_uno"
    )
    assert recovered["estop_latched"] is False
    assert recovered["last_error_code"] is None
