"""CODEX hardware orchestration: health FSM, 16-step pre-flight, prepare/execute, and E-STOP."""

from __future__ import annotations

import difflib
import logging
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.audit import log_audit
from app.core.config import settings
from app.integrations.codex.client import CodexTransport, get_codex_transport
from app.integrations.codex.protocol import (
    UART_MSG_ESTOP,
    UART_MSG_MOTION_CMD,
    build_codex_command_payload,
    build_signed_headers,
    compute_payload_sha256,
    encode_uno_motion_payload,
    encode_uno_uart_frame,
    generate_command_nonce,
    redact_sensitive_mapping,
)
from app.models.codex import (
    CodexCommandNonce,
    HardwareConfiguration,
    HardwareDevice,
    HardwareRun,
    MoonLedRegion,
    MotorCalibrationProfile,
)
from app.repositories import codex_repo
from app.services.codex_kinematics import (
    CalibrationSpec,
    KinematicsError,
    compute_kepler_orbital_reference,
    compute_motor_move_plan,
    extract_orbital_target_angles_deg,
    resolve_physical_duration_seconds,
)
from app.services.codex_template_engine import (
    RAW_TOKEN_PATTERN,
    PlaceholderSpec,
    TemplateRenderError,
    compute_sha256_hex,
    render_firmware_template,
)
from app.services.moon_led_mapping import (
    LedMappingError,
    LedPixelOutput,
    LedRegionDefinition,
    resolve_site_to_moon_led_region,
)

logger = logging.getLogger("clps_luna_browser.codex.service")

ALL_CONTROLLER_KEYS = ("wifi_bridge", "motion_uno", "moon_led_s3")
MOTION_CONTROLLER_KEYS = ("wifi_bridge", "motion_uno")
LED_CONTROLLER_KEYS = ("moon_led_s3",)


@dataclass(frozen=True)
class EffectiveDeviceHealth:
    """Evaluated health state of one CODEX controller combining DB telemetry and safety rules."""

    controller_key: str
    effective_state: str
    heartbeat_fresh: bool
    is_ready_for_run: bool
    blockers: list[str]
    device: HardwareDevice


def _calibration_to_spec(model: MotorCalibrationProfile) -> CalibrationSpec:
    """Adapt ORM MotorCalibrationProfile row into typed kinematic CalibrationSpec."""
    return CalibrationSpec(
        motor_key=model.motor_key or model.motor_name.lower(),
        controller_key=model.controller_key,
        motor_name=model.motor_name,
        calibration_version=model.calibration_version,
        verification_status=model.verification_status,
        gear_reduction_ratio=float(model.gear_reduction_ratio),
        full_steps_per_rev=int(model.full_steps_per_rev),
        microsteps=int(model.microsteps),
        direction_sign=int(model.direction_sign),
        max_step_rate=int(model.max_step_rate),
        acceleration=int(model.acceleration),
        backlash_steps=int(model.backlash_steps or 0),
        zero_offset_deg=float(model.zero_offset_deg or 0.0),
        travel_min_deg=model.travel_min_deg,
        travel_max_deg=model.travel_max_deg,
        motor_model=model.motor_model,
        driver_model=model.driver_model,
    )


def _regions_to_definitions(db: Session) -> list[LedRegionDefinition]:
    """Load active Moon LED regions and normalized pixels cleanly."""
    regions = codex_repo.list_moon_led_regions(db, active_only=True)
    all_pixels = codex_repo.list_moon_led_region_pixels(db, active_only=True)
    px_by_region: dict[int, list[LedPixelOutput]] = {}
    for row in all_pixels:
        px_by_region.setdefault(row.region_id, []).append(
            LedPixelOutput(
                pixel_index=row.pixel_index,
                output_channel=row.output_channel,
                pixel_order=row.pixel_order,
                topology_mode=row.topology_mode,
                verification_status=row.verification_status,
            )
        )
    defs: list[LedRegionDefinition] = []
    for r in regions:
        defs.append(
            LedRegionDefinition(
                region_index=r.region_index,
                region_name=r.region_name,
                mapping_version=r.mapping_version,
                verification_status=r.verification_status,
                centroid_lat_deg=float(r.centroid_lat) if r.centroid_lat is not None else None,
                centroid_lon_deg=float(r.centroid_lon) if r.centroid_lon is not None else None,
                boundary_polygon=r.boundary_polygon,
                pixel_indices=list(r.pixel_indices or []),
                orientation_reference=r.orientation_reference,
                geometry_source=r.geometry_source,
                normalized_pixels=px_by_region.get(r.region_id, []),
                is_active=bool(r.is_active),
            )
        )
    return defs


def evaluate_controller_health(
    device: HardwareDevice,
    *,
    active_config: HardwareConfiguration | None,
    nema_cal: MotorCalibrationProfile | None,
    byj_cal: MotorCalibrationProfile | None,
    require_verified_bench: bool,
) -> EffectiveDeviceHealth:
    """Evaluate controller FSM state against heartbeat TTL, firmware, config, and calibration."""
    now = codex_repo.utc_now()
    blockers: list[str] = []

    if device.last_heartbeat_at is None:
        fresh = False
    else:
        age_s = (now - device.last_heartbeat_at).total_seconds()
        fresh = age_s <= float(settings.CODEX_HEARTBEAT_STALE_SECONDS)

    if device.estop_latched:
        blockers.append(f"{device.controller_key}: e-stop latched")
        return EffectiveDeviceHealth(
            controller_key=device.controller_key,
            effective_state="fault",
            heartbeat_fresh=fresh,
            is_ready_for_run=False,
            blockers=blockers,
            device=device,
        )

    if not fresh or device.health_state == "offline":
        blockers.append(f"{device.controller_key}: offline or heartbeat stale")
        return EffectiveDeviceHealth(
            controller_key=device.controller_key,
            effective_state="offline",
            heartbeat_fresh=False,
            is_ready_for_run=False,
            blockers=blockers,
            device=device,
        )

    if device.health_state == "busy":
        blockers.append(f"{device.controller_key}: busy executing active command")
        return EffectiveDeviceHealth(
            controller_key=device.controller_key,
            effective_state="busy",
            heartbeat_fresh=True,
            is_ready_for_run=False,
            blockers=blockers,
            device=device,
        )

    if device.health_state == "fault" or device.last_error_code in (
        "ack_fault",
        "timeout",
        "fault",
    ):
        blockers.append(
            f"{device.controller_key}: fault ({device.last_error_message or device.last_error_code or 'unknown'})"
        )
        return EffectiveDeviceHealth(
            controller_key=device.controller_key,
            effective_state="fault",
            heartbeat_fresh=True,
            is_ready_for_run=False,
            blockers=blockers,
            device=device,
        )

    if (
        device.expected_firmware_version
        and device.reported_firmware_version != device.expected_firmware_version
    ):
        blockers.append(
            f"{device.controller_key}: firmware mismatch "
            f"(expected={device.expected_firmware_version}, reported={device.reported_firmware_version})"
        )
        return EffectiveDeviceHealth(
            controller_key=device.controller_key,
            effective_state="firmware_mismatch",
            heartbeat_fresh=True,
            is_ready_for_run=False,
            blockers=blockers,
            device=device,
        )

    if active_config is not None and active_config.board_model != device.board_model:
        blockers.append(
            f"{device.controller_key}: configuration mismatch "
            f"(board_model config={active_config.board_model}, device={device.board_model})"
        )
        return EffectiveDeviceHealth(
            controller_key=device.controller_key,
            effective_state="configuration_mismatch",
            heartbeat_fresh=True,
            is_ready_for_run=False,
            blockers=blockers,
            device=device,
        )

    if device.controller_key in MOTION_CONTROLLER_KEYS and not device.uart_ok:
        blockers.append(f"{device.controller_key}: Uno UART link unhealthy")
        return EffectiveDeviceHealth(
            controller_key=device.controller_key,
            effective_state="fault",
            heartbeat_fresh=True,
            is_ready_for_run=False,
            blockers=blockers,
            device=device,
        )

    if device.controller_key == "motion_uno":
        if not device.driver_config_ok:
            blockers.append("motion_uno: driver configuration check not confirmed")
            return EffectiveDeviceHealth(
                controller_key="motion_uno",
                effective_state="configuration_mismatch",
                heartbeat_fresh=True,
                is_ready_for_run=False,
                blockers=blockers,
                device=device,
            )
        missing_or_unverified = (
            nema_cal is None
            or byj_cal is None
            or (
                require_verified_bench
                and (
                    nema_cal.verification_status != "bench_verified"
                    or byj_cal.verification_status != "bench_verified"
                )
            )
        )
        if missing_or_unverified:
            blockers.append("motion_uno: bench-verified NEMA17/BYJ calibration missing")
            return EffectiveDeviceHealth(
                controller_key="motion_uno",
                effective_state="calibration_missing",
                heartbeat_fresh=True,
                is_ready_for_run=False,
                blockers=blockers,
                device=device,
            )

    if device.controller_key == "moon_led_s3" and not device.led_controller_ok:
        blockers.append("moon_led_s3: LED controller health check failed")
        return EffectiveDeviceHealth(
            controller_key="moon_led_s3",
            effective_state="fault",
            heartbeat_fresh=True,
            is_ready_for_run=False,
            blockers=blockers,
            device=device,
        )

    if device.verification_status == "quarantined":
        blockers.append(f"{device.controller_key}: device quarantined by admin")
        return EffectiveDeviceHealth(
            controller_key=device.controller_key,
            effective_state="fault",
            heartbeat_fresh=True,
            is_ready_for_run=False,
            blockers=blockers,
            device=device,
        )

    if require_verified_bench and device.verification_status != "bench_verified":
        blockers.append(f"{device.controller_key}: online but unverified")
        return EffectiveDeviceHealth(
            controller_key=device.controller_key,
            effective_state="online_unverified",
            heartbeat_fresh=True,
            is_ready_for_run=False,
            blockers=blockers,
            device=device,
        )

    state = "completed" if device.health_state == "completed" else "ready"
    return EffectiveDeviceHealth(
        controller_key=device.controller_key,
        effective_state=state,
        heartbeat_fresh=True,
        is_ready_for_run=True,
        blockers=[],
        device=device,
    )


def _gather_health_map(
    db: Session, *, require_verified_bench: bool | None = None
) -> dict[str, EffectiveDeviceHealth]:
    """Compute effective health state for all registered CODEX controllers."""
    strict = (
        settings.CODEX_REQUIRE_VERIFIED_BENCH
        if require_verified_bench is None
        else require_verified_bench
    )
    devices = codex_repo.list_hardware_devices(db)
    configs = {c.controller_key: c for c in codex_repo.list_active_configurations(db)}
    nema_cal = codex_repo.get_active_motor_calibration(db, "nema17")
    byj_cal = codex_repo.get_active_motor_calibration(db, "byj")
    return {
        dev.controller_key: evaluate_controller_health(
            dev,
            active_config=configs.get(dev.controller_key),
            nema_cal=nema_cal,
            byj_cal=byj_cal,
            require_verified_bench=strict,
        )
        for dev in devices
    }


def _to_public_controller_dict(health: EffectiveDeviceHealth) -> dict[str, Any]:
    dev = health.device
    return {
        "controller_key": dev.controller_key,
        "device_role": dev.device_role,
        "board_model": dev.board_model,
        "health_state": health.effective_state,
        "verification_status": dev.verification_status,
        "heartbeat_fresh": health.heartbeat_fresh,
        "uart_ok": bool(dev.uart_ok),
        "driver_config_ok": bool(dev.driver_config_ok),
        "led_controller_ok": bool(dev.led_controller_ok),
        "estop_latched": bool(dev.estop_latched),
        "battery_voltage_available": bool(dev.battery_voltage_available),
        "battery_voltage_v": dev.battery_voltage_v if dev.battery_voltage_available else None,
        "last_heartbeat_at": dev.last_heartbeat_at,
    }


def get_public_status_payload(db: Session) -> dict[str, Any]:
    """Return non-sensitive CODEX status summary for public frontend status pills."""
    health_map = _gather_health_map(db)
    nema_cal = codex_repo.get_active_motor_calibration(db, "nema17")
    byj_cal = codex_repo.get_active_motor_calibration(db, "byj")
    regions = codex_repo.list_moon_led_regions(db, active_only=True)

    motors_ready = all(
        key in health_map and health_map[key].is_ready_for_run for key in MOTION_CONTROLLER_KEYS
    )
    led_ready = "moon_led_s3" in health_map and health_map["moon_led_s3"].is_ready_for_run
    estop_latched = any(h.device.estop_latched for h in health_map.values())
    cal_verified = bool(
        nema_cal
        and byj_cal
        and nema_cal.verification_status == "bench_verified"
        and byj_cal.verification_status == "bench_verified"
    )
    led_verified = bool(regions) and any(r.verification_status == "bench_verified" for r in regions)

    blockers: list[str] = []
    for h in health_map.values():
        blockers.extend(h.blockers)
    if not regions:
        blockers.append("moon_led: 13-region physical LED map not populated")

    if estop_latched:
        overall = "estop_latched"
    elif motors_ready and led_ready:
        overall = "ready"
    elif led_ready and not motors_ready:
        overall = "degraded_led_only"
    elif any(h.effective_state == "fault" for h in health_map.values()):
        overall = "fault"
    else:
        overall = "not_ready"

    return {
        "transport_mode": settings.CODEX_TRANSPORT_MODE,
        "require_verified_bench": settings.CODEX_REQUIRE_VERIFIED_BENCH,
        "overall_status": overall,
        "motors_ready": motors_ready,
        "led_ready": led_ready,
        "estop_latched": estop_latched,
        "calibration_verified": cal_verified,
        "led_mapping_verified": led_verified,
        "blockers": blockers,
        "controllers": [_to_public_controller_dict(health_map[k]) for k in sorted(health_map)],
        "checked_at": codex_repo.utc_now(),
    }


def get_admin_devices_payload(db: Session) -> dict[str, Any]:
    """Return full administrative diagnostics including hosts, firmware identity, and configs."""
    health_map = _gather_health_map(db)
    configs = codex_repo.list_active_configurations(db)
    devices_out: list[dict[str, Any]] = []
    for key in sorted(health_map):
        h = health_map[key]
        dev = h.device
        entry = _to_public_controller_dict(h)
        entry.update(
            {
                "device_id": dev.device_id,
                "endpoint_host": dev.endpoint_host,
                "endpoint_port": dev.endpoint_port,
                "transport_type": dev.transport_type,
                "expected_firmware_version": dev.expected_firmware_version,
                "reported_firmware_version": dev.reported_firmware_version,
                "reported_firmware_checksum": dev.reported_firmware_checksum,
                "last_handshake_at": dev.last_handshake_at,
                "ping_latency_ms": dev.ping_latency_ms,
                "last_error_code": dev.last_error_code,
                "last_error_message": dev.last_error_message,
                "device_metadata": dev.device_metadata or {},
                "updated_at": dev.updated_at,
            }
        )
        devices_out.append(entry)

    cfg_out = [
        {
            "hardware_config_id": str(c.hardware_config_id),
            "controller_key": c.controller_key,
            "board_model": c.board_model,
            "firmware_target": c.firmware_target,
            "motor_type": c.motor_type,
            "driver_model": c.driver_model,
            "led_count": c.led_count,
            "led_mapping_version": c.led_mapping_version,
            "updated_at": (
                c.updated_at.isoformat()
                if isinstance(c.updated_at, datetime)
                else (str(c.updated_at) if c.updated_at else None)
            ),
        }
        for c in configs
    ]
    return {
        "transport_mode": settings.CODEX_TRANSPORT_MODE,
        "require_verified_bench": settings.CODEX_REQUIRE_VERIFIED_BENCH,
        "devices": devices_out,
        "configurations": cfg_out,
        "checked_at": codex_repo.utc_now(),
    }


def update_device_heartbeat(
    db: Session,
    *,
    controller_key: str,
    payload: dict[str, Any],
    admin_id: UUID | None = None,
    transport: CodexTransport | None = None,
) -> dict[str, Any]:
    """Probe via configured transport or apply pushed telemetry and recompute health FSM."""
    device = codex_repo.get_hardware_device(db, controller_key)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown CODEX controller '{controller_key}'.",
        )

    now = codex_repo.utc_now()
    if payload.get("expected_firmware_version") is not None:
        device.expected_firmware_version = payload["expected_firmware_version"]
    if payload.get("verification_status") is not None:
        device.verification_status = payload["verification_status"]
    if payload.get("reset_estop_latch"):
        device.estop_latched = False
        device.last_error_code = None
        device.last_error_message = None

    if payload.get("probe_via_transport", True):
        active_transport = transport or get_codex_transport()
        probe = active_transport.probe_device(
            controller_key=device.controller_key,
            endpoint_host=device.endpoint_host,
            endpoint_port=device.endpoint_port,
            expected_firmware_version=device.expected_firmware_version,
            device_metadata=device.device_metadata,
        )
        device.ping_latency_ms = probe.ping_latency_ms
        if probe.online:
            device.last_heartbeat_at = now
            device.last_handshake_at = now
            device.reported_firmware_version = probe.reported_firmware_version
            device.reported_firmware_checksum = probe.reported_firmware_checksum
            device.uart_ok = probe.uart_ok
            device.driver_config_ok = probe.driver_config_ok
            device.led_controller_ok = probe.led_controller_ok
            if probe.estop_latched:
                device.estop_latched = True
            device.battery_voltage_available = probe.battery_voltage_available
            device.battery_voltage_v = (
                probe.battery_voltage_v if probe.battery_voltage_available else None
            )
            device.last_error_code = probe.error_code
            device.last_error_message = probe.error_message
            if device.health_state in ("offline", "completed"):
                device.health_state = "ready"
        else:
            device.health_state = "offline"
            device.last_error_code = probe.error_code
            device.last_error_message = probe.error_message
    else:
        device.last_heartbeat_at = now
        device.last_handshake_at = now
        for fld in (
            "reported_firmware_version",
            "reported_firmware_checksum",
            "uart_ok",
            "driver_config_ok",
            "led_controller_ok",
            "ping_latency_ms",
            "last_error_code",
            "last_error_message",
        ):
            if payload.get(fld) is not None:
                setattr(device, fld, payload[fld])
        if payload.get("estop_latched") is True:
            device.estop_latched = True
        if payload.get("battery_voltage_available") is True:
            device.battery_voltage_available = True
            device.battery_voltage_v = payload.get("battery_voltage_v")
        elif payload.get("battery_voltage_available") is False:
            device.battery_voltage_available = False
            device.battery_voltage_v = None
        if device.health_state == "offline" and not device.estop_latched:
            device.health_state = "ready"

    db.flush()
    health_map = _gather_health_map(db)
    resolved = health_map[controller_key]
    if resolved.effective_state != device.health_state and device.health_state != "busy":
        device.health_state = resolved.effective_state

    log_audit(
        db,
        action_key="CODEX_DEVICE_HEARTBEAT",
        entity_type="hardware_device",
        entity_id=controller_key,
        admin_id=str(admin_id) if admin_id else None,
        after_snapshot={
            "health_state": resolved.effective_state,
            "verification_status": device.verification_status,
            "reported_firmware": device.reported_firmware_version,
        },
    )
    db.commit()
    return get_admin_devices_payload(db)


def create_calibration_profile(
    db: Session,
    *,
    payload: dict[str, Any],
    admin_id: UUID | None = None,
) -> MotorCalibrationProfile:
    """Persist a new immutable motor calibration version without overwriting history."""
    if payload["verification_status"] == "bench_verified" and not payload.get("measured_by"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="bench_verified calibration profiles require measured_by provenance.",
        )
    data = dict(payload)
    activate = bool(data.pop("activate", True))
    if data["verification_status"] == "bench_verified":
        data["measured_at"] = codex_repo.utc_now()
    row, superseded_id = codex_repo.create_versioned_motor_calibration(
        db, payload=data, activate=activate
    )
    log_audit(
        db,
        action_key="CODEX_CALIBRATION_CREATE",
        entity_type="motor_calibration_profile",
        entity_id=str(row.calibration_id),
        admin_id=str(admin_id) if admin_id else None,
        after_snapshot={
            "motor_key": row.motor_key,
            "calibration_version": row.calibration_version,
            "verification_status": row.verification_status,
            "supersedes": superseded_id,
        },
    )
    db.commit()
    db.refresh(row)
    return row


def update_calibration_status(
    db: Session,
    *,
    calibration_id: int,
    verification_status: str,
    calibration_notes: str | None,
    measured_by: str | None,
    is_active: bool | None,
    admin_id: UUID | None = None,
) -> MotorCalibrationProfile:
    """Update verification/deprecation status on a calibration profile with audit trail."""
    row = codex_repo.get_motor_calibration_by_id(db, calibration_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Calibration profile {calibration_id} not found.",
        )
    before = {
        "verification_status": row.verification_status,
        "is_active": row.is_active,
    }
    if verification_status == "bench_verified" and not (measured_by or row.measured_by):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Promoting a calibration profile to bench_verified requires measured_by.",
        )
    row.verification_status = verification_status
    if verification_status == "bench_verified":
        row.measured_at = row.measured_at or codex_repo.utc_now()
    if measured_by is not None:
        row.measured_by = measured_by
    if calibration_notes is not None:
        row.calibration_notes = calibration_notes
    if is_active is not None:
        row.is_active = is_active

    log_audit(
        db,
        action_key="CODEX_CALIBRATION_UPDATE",
        entity_type="motor_calibration_profile",
        entity_id=str(calibration_id),
        admin_id=str(admin_id) if admin_id else None,
        before_snapshot=before,
        after_snapshot={
            "verification_status": row.verification_status,
            "is_active": row.is_active,
        },
    )
    db.commit()
    db.refresh(row)
    return row


def upsert_moon_led_region(
    db: Session,
    *,
    payload: dict[str, Any],
    admin_id: UUID | None = None,
) -> tuple[MoonLedRegion, list[dict[str, Any]]]:
    """Create or update a 1..13 Moon LED region and normalized pixel assignments."""
    region = codex_repo.upsert_moon_led_region_with_pixels(db, **payload)
    log_audit(
        db,
        action_key="CODEX_LED_MAPPING_UPSERT",
        entity_type="moon_led_region",
        entity_id=str(region.region_index),
        admin_id=str(admin_id) if admin_id else None,
        after_snapshot={
            "region_index": region.region_index,
            "mapping_version": region.mapping_version,
            "verification_status": region.verification_status,
            "pixel_indices": list(region.pixel_indices or []),
        },
    )
    db.commit()
    db.refresh(region)
    pixels = [
        {
            "pixel_index": p.pixel_index,
            "output_channel": p.output_channel,
            "pixel_order": p.pixel_order,
            "topology_mode": p.topology_mode,
            "verification_status": p.verification_status,
        }
        for p in codex_repo.list_moon_led_region_pixels(db, region_id=region.region_id)
    ]
    return region, pixels


def list_moon_led_regions_payload(db: Session) -> list[dict[str, Any]]:
    """Serialize all Moon LED regions and normalized pixel targets."""
    regions = codex_repo.list_moon_led_regions(db, active_only=False)
    pixels = codex_repo.list_moon_led_region_pixels(db, active_only=True)
    px_map: dict[int, list[dict[str, Any]]] = {}
    for p in pixels:
        px_map.setdefault(p.region_id, []).append(
            {
                "pixel_index": p.pixel_index,
                "output_channel": p.output_channel,
                "pixel_order": p.pixel_order,
                "topology_mode": p.topology_mode,
                "verification_status": p.verification_status,
            }
        )
    return [
        {
            "region_id": r.region_id,
            "region_index": r.region_index,
            "region_name": r.region_name,
            "centroid_lat": float(r.centroid_lat) if r.centroid_lat is not None else None,
            "centroid_lon": float(r.centroid_lon) if r.centroid_lon is not None else None,
            "boundary_polygon": r.boundary_polygon,
            "pixel_indices": list(r.pixel_indices or []),
            "mapping_version": r.mapping_version,
            "orientation_reference": r.orientation_reference,
            "verification_status": r.verification_status,
            "geometry_source": r.geometry_source,
            "is_active": bool(r.is_active),
            "normalized_pixels": px_map.get(r.region_id, []),
        }
        for r in regions
    ]


def _evaluate_16_step_preflight(
    db: Session,
    *,
    execution_mode: str,
    physical_duration_seconds: int | None,
    clamp_to_travel_limits: bool,
    allow_unverified_preview: bool,
    allow_centroid_led_fallback: bool,
    site_id: int,
    simulation_id: UUID,
    require_confirmed: bool,
    confirmed: bool,
) -> dict[str, Any]:
    """Run deterministic 16-step CODEX pre-flight validation and motion/LED planning."""
    strict_bench = settings.CODEX_REQUIRE_VERIFIED_BENCH
    target_controllers = (
        list(LED_CONTROLLER_KEYS) if execution_mode == "led_only" else list(ALL_CONTROLLER_KEYS)
    )
    steps: list[dict[str, Any]] = []

    def _add_step(num: int, key: str, passed: bool, severity: str, detail: str) -> None:
        steps.append(
            {
                "step_number": num,
                "key": key,
                "passed": passed,
                "severity": "ok" if passed else severity,
                "detail": detail,
            }
        )

    site = codex_repo.get_published_site(db, site_id)
    site_ok = site is not None and site.catalogue_status == "published"
    _add_step(
        1,
        "site_published",
        site_ok,
        "blocker",
        "Site is published." if site_ok else "Landing site missing or not published.",
    )

    sim = codex_repo.get_simulation_run(db, simulation_id)
    sim_ok = sim is not None and sim.site_id == site_id and sim.status == "completed"
    _add_step(
        2,
        "simulation_valid",
        sim_ok,
        "blocker",
        "Completed single-site simulation verified."
        if sim_ok
        else "Simulation missing, belongs to a different site, or is not completed.",
    )

    # Compute time separation + physical duration bounds
    resolved_phys_s = physical_duration_seconds or 15
    time_ok = False
    kepler_ref: dict[str, Any] = {}
    if sim is not None:
        try:
            resolved_phys_s = resolve_physical_duration_seconds(
                int(sim.duration_seconds),
                float(sim.playback_speed or 1.0),
                physical_duration_seconds,
            )
            kepler_ref = compute_kepler_orbital_reference(int(sim.duration_seconds))
            time_ok = True
        except KinematicsError as exc:
            _add_step(3, "time_parameters_valid", False, "blocker", exc.message)
        else:
            _add_step(
                3,
                "time_parameters_valid",
                True,
                "ok",
                f"SPICE span={sim.duration_seconds}s separated from physical_duration={resolved_phys_s}s.",
            )
    else:
        _add_step(
            3, "time_parameters_valid", False, "blocker", "Cannot resolve time without simulation."
        )

    health_map = _gather_health_map(db, require_verified_bench=strict_bench)
    missing_devs = [k for k in target_controllers if k not in health_map]
    _add_step(
        4,
        "device_inventory_present",
        len(missing_devs) == 0,
        "blocker",
        f"Controllers registered: {target_controllers}."
        if not missing_devs
        else f"Missing registered controllers: {missing_devs}.",
    )

    stale = [k for k in target_controllers if k in health_map and not health_map[k].heartbeat_fresh]
    _add_step(
        5,
        "device_heartbeat_fresh",
        len(stale) == 0,
        "blocker",
        "All target heartbeats are within TTL."
        if not stale
        else f"Offline/stale heartbeat controllers: {stale}.",
    )

    unverified_devs = [
        k
        for k in target_controllers
        if k in health_map
        and strict_bench
        and health_map[k].device.verification_status != "bench_verified"
    ]
    _add_step(
        6,
        "device_verification_status",
        len(unverified_devs) == 0,
        "blocker",
        "All target controllers are bench_verified."
        if not unverified_devs
        else f"Unverified target controllers: {unverified_devs}.",
    )

    fw_bad = [
        k
        for k in target_controllers
        if k in health_map and health_map[k].effective_state == "firmware_mismatch"
    ]
    _add_step(
        7,
        "firmware_version_match",
        len(fw_bad) == 0,
        "blocker",
        "Reported firmware versions match expectations."
        if not fw_bad
        else f"Firmware version mismatch on: {fw_bad}.",
    )

    if execution_mode == "led_only":
        _add_step(
            8,
            "bridge_uart_link_ok",
            True,
            "ok",
            "Not required in led_only mode (bypassed safely).",
        )
    else:
        uart_bad = [
            k
            for k in MOTION_CONTROLLER_KEYS
            if k in health_map and not health_map[k].device.uart_ok
        ]
        _add_step(
            8,
            "bridge_uart_link_ok",
            len(uart_bad) == 0,
            "blocker",
            "ESP32 <-> Uno UART health verified."
            if not uart_bad
            else f"Uno UART link unhealthy on: {uart_bad}.",
        )

    configs = {c.controller_key: c for c in codex_repo.list_active_configurations(db)}
    cfg_bad = [
        k
        for k in target_controllers
        if (k not in configs)
        or (k in health_map and health_map[k].effective_state == "configuration_mismatch")
    ]
    _add_step(
        9,
        "configuration_present",
        len(cfg_bad) == 0,
        "blocker",
        "Active hardware configuration baselines match devices."
        if not cfg_bad
        else f"Missing or mismatched hardware_configurations for: {cfg_bad}.",
    )

    nema_cal = codex_repo.get_active_motor_calibration(db, "nema17")
    byj_cal = codex_repo.get_active_motor_calibration(db, "byj")
    if execution_mode == "led_only":
        _add_step(10, "nema17_calibration_valid", True, "ok", "Skipped in led_only mode.")
        _add_step(11, "byj_calibration_valid", True, "ok", "Skipped in led_only mode.")
    else:
        nema_ok = nema_cal is not None and (
            not strict_bench or nema_cal.verification_status == "bench_verified"
        )
        _add_step(
            10,
            "nema17_calibration_valid",
            nema_ok,
            "blocker",
            f"NEMA17 calibration '{nema_cal.calibration_version}' verified."
            if nema_ok and nema_cal
            else "Missing or unverified NEMA17 motor calibration profile.",
        )
        byj_ok = byj_cal is not None and (
            not strict_bench or byj_cal.verification_status == "bench_verified"
        )
        _add_step(
            11,
            "byj_calibration_valid",
            byj_ok,
            "blocker",
            f"BYJ calibration '{byj_cal.calibration_version}' verified."
            if byj_ok and byj_cal
            else "Missing or unverified BYJ motor calibration profile.",
        )

    # Extract orbital target angles and compute motor plans (in led_only, no motor steps issued)
    orbital_targets: dict[str, float] = {}
    motor_plans_dict: dict[str, Any] | None = None
    kin_warnings: list[str] = []
    if site is not None:
        sample = codex_repo.get_simulation_terminal_sample(db, simulation_id)
        sun_xyz = (
            (sample.sun_dir_moon_x, sample.sun_dir_moon_y, sample.sun_dir_moon_z)
            if sample is not None
            else None
        )
        earth_xyz = (
            (sample.earth_dir_moon_x, sample.earth_dir_moon_y, sample.earth_dir_moon_z)
            if sample is not None
            else None
        )
        orbital_targets = extract_orbital_target_angles_deg(
            site_lat_deg=float(site.latitude_deg),
            site_lon_deg=float(site.longitude_deg),
            sun_dir_moon_xyz=sun_xyz,
            earth_dir_moon_xyz=earth_xyz,
        )

    if execution_mode == "led_only":
        _add_step(12, "kinematics_within_limits", True, "ok", "Skipped in led_only mode.")
    else:
        if nema_cal is None or byj_cal is None or not time_ok or site is None:
            _add_step(
                12,
                "kinematics_within_limits",
                False,
                "blocker",
                "Cannot compute kinematics without valid site, timing, NEMA17 & BYJ calibrations.",
            )
        else:
            try:
                # Allow unverified calculation preview only when requested during prepare dry-run
                req_ver_math = strict_bench and not allow_unverified_preview
                nema_plan = compute_motor_move_plan(
                    _calibration_to_spec(nema_cal),
                    target_angle_deg=orbital_targets["nema17_arm_angle_deg"],
                    permitted_move_seconds=float(resolved_phys_s),
                    require_verified=req_ver_math,
                    clamp_to_travel_limits=clamp_to_travel_limits,
                )
                byj_plan = compute_motor_move_plan(
                    _calibration_to_spec(byj_cal),
                    target_angle_deg=orbital_targets["byj_earth_frame_deg"],
                    permitted_move_seconds=float(resolved_phys_s),
                    require_verified=req_ver_math,
                    clamp_to_travel_limits=clamp_to_travel_limits,
                )
                motor_plans_dict = {
                    "permitted_move_seconds": resolved_phys_s,
                    "nema17": nema_plan.to_dict(),
                    "byj": byj_plan.to_dict(),
                }
                kin_warnings.extend(nema_plan.warnings)
                kin_warnings.extend(byj_plan.warnings)
                kin_verified_ok = (not strict_bench) or (
                    nema_cal.verification_status == "bench_verified"
                    and byj_cal.verification_status == "bench_verified"
                )
                _add_step(
                    12,
                    "kinematics_within_limits",
                    kin_verified_ok,
                    "blocker",
                    "Trapezoidal step counts and rates within motor/driver bounds."
                    if kin_verified_ok
                    else "Dry-run kinematics computed, but calibrations are not bench_verified.",
                )
            except KinematicsError as exc:
                _add_step(12, "kinematics_within_limits", False, "blocker", exc.message)

    # Step 13: 13-region Moon LED resolution
    moon_led_dict: dict[str, Any] | None = None
    led_warnings: list[str] = []
    if site is not None:
        regions = _regions_to_definitions(db)
        try:
            # First try strict verification status check when executing; allow preview fallback if requested
            led_res = resolve_site_to_moon_led_region(
                site_lat_deg=float(site.latitude_deg),
                site_lon_deg=float(site.longitude_deg),
                regions=regions,
                require_verified_mapping=strict_bench and not allow_unverified_preview,
                allow_centroid_fallback=allow_centroid_led_fallback or allow_unverified_preview,
            )
            moon_led_dict = led_res.to_dict()
            led_warnings.extend(led_res.warnings)
            led_ok = (not strict_bench) or led_res.is_verified_for_hardware
            _add_step(
                13,
                "led_mapping_valid",
                led_ok,
                "blocker",
                f"Resolved Region {led_res.region_index} ({led_res.region_name}) pixels={led_res.pixel_indices}."
                if led_ok
                else f"Region {led_res.region_index} resolved in preview only ({led_res.mapping_mode}, status={led_res.verification_status}).",
            )
        except LedMappingError as exc:
            _add_step(13, "led_mapping_valid", False, "blocker", exc.message)
    else:
        _add_step(13, "led_mapping_valid", False, "blocker", "Site required for Moon LED mapping.")

    estop_devs = [
        k for k in target_controllers if k in health_map and health_map[k].device.estop_latched
    ]
    _add_step(
        14,
        "estop_not_latched",
        len(estop_devs) == 0,
        "blocker",
        "No emergency-stop latches active."
        if not estop_devs
        else f"E-STOP latched on: {estop_devs}. Clear latch before execution.",
    )

    secret_ok = (
        len(settings.CODEX_SHARED_SECRET.strip()) >= 16 and settings.CODEX_COMMAND_TTL_SECONDS > 0
    )
    _add_step(
        15,
        "replay_and_ttl_ready",
        secret_ok,
        "blocker",
        f"HMAC-SHA256 key loaded, TTL={settings.CODEX_COMMAND_TTL_SECONDS}s."
        if secret_ok
        else "CODEX shared secret too short or TTL invalid.",
    )

    conf_ok = (not require_confirmed) or bool(confirmed)
    _add_step(
        16,
        "operator_confirmation_policy",
        conf_ok,
        "blocker",
        "Explicit operator confirmation granted."
        if require_confirmed and conf_ok
        else (
            "Preparation preview only; execution requires explicit confirmation."
            if not require_confirmed
            else "Execution denied without confirmed=True."
        ),
    )

    blockers = [s["detail"] for s in steps if not s["passed"]]
    warnings = list(dict.fromkeys(kin_warnings + led_warnings))
    ready_to_execute = len(blockers) == 0

    cfg_version = (
        ",".join(
            f"{k}:{str(configs[k].hardware_config_id)[:8]}"
            for k in sorted(target_controllers)
            if k in configs
        )
        or "unconfigured"
    )
    cal_version = (
        f"nema:{nema_cal.calibration_version}|byj:{byj_cal.calibration_version}"
        if (execution_mode != "led_only" and nema_cal and byj_cal)
        else ("led_only" if execution_mode == "led_only" else "unverified")
    )
    led_version = moon_led_dict["mapping_version"] if moon_led_dict else "unmapped"

    return {
        "site": site,
        "sim": sim,
        "physical_duration_seconds": resolved_phys_s,
        "kepler_reference": kepler_ref,
        "orbital_targets_deg": orbital_targets,
        "motor_plans": motor_plans_dict,
        "moon_led_plan": moon_led_dict,
        "target_controllers": target_controllers,
        "configuration_version": cfg_version,
        "calibration_version": cal_version,
        "led_mapping_version": led_version,
        "configs_snapshot": {
            k: {
                "hardware_config_id": str(configs[k].hardware_config_id),
                "board_model": configs[k].board_model,
                "firmware_target": configs[k].firmware_target,
            }
            for k in sorted(configs)
        },
        "steps": steps,
        "passed_count": sum(1 for s in steps if s["passed"]),
        "total_steps": len(steps),
        "blockers": blockers,
        "warnings": warnings,
        "ready_to_execute": ready_to_execute,
    }


def prepare_codex_run(
    db: Session,
    *,
    payload: dict[str, Any],
    operator_admin_id: UUID | None = None,
) -> dict[str, Any]:
    """Run kinematics, Moon LED mapping, and 16-step pre-flight WITHOUT actuating hardware."""
    sim_id: UUID = payload["simulation_id"]
    sim = codex_repo.get_simulation_run(db, sim_id)
    if sim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Simulation {sim_id} not found.",
        )

    site = codex_repo.get_published_site(db, sim.site_id)
    if site is None or site.catalogue_status != "published":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Simulation belongs to an unpublished or missing landing site.",
        )

    pf = _evaluate_16_step_preflight(
        db,
        execution_mode=payload.get("execution_mode", "full_codex"),
        physical_duration_seconds=payload.get("physical_duration_seconds"),
        clamp_to_travel_limits=bool(payload.get("clamp_to_travel_limits", False)),
        allow_unverified_preview=bool(payload.get("allow_unverified_preview", True)),
        allow_centroid_led_fallback=bool(payload.get("allow_centroid_led_fallback", False)),
        site_id=sim.site_id,
        simulation_id=sim_id,
        require_confirmed=False,
        confirmed=False,
    )

    prepared_blob = {
        "execution_mode": payload.get("execution_mode", "full_codex"),
        "simulation_duration_seconds": int(sim.duration_seconds),
        "playback_speed": float(sim.playback_speed or 1.0),
        "physical_duration_seconds": pf["physical_duration_seconds"],
        "kepler_reference": pf["kepler_reference"],
        "orbital_targets_deg": pf["orbital_targets_deg"],
        "motor_plans": pf["motor_plans"],
        "moon_led_plan": pf["moon_led_plan"],
        "target_controllers": pf["target_controllers"],
        "preflight_passed_count": pf["passed_count"],
        "preflight_total_steps": pf["total_steps"],
        "blockers": pf["blockers"],
        "warnings": pf["warnings"],
        "ready_to_execute": pf["ready_to_execute"],
    }

    run = HardwareRun(
        simulation_id=sim.simulation_id,
        site_id=sim.site_id,
        start_time_utc=sim.start_time_utc,
        duration_seconds=sim.duration_seconds,
        prepared_payload=prepared_blob,
        hardware_config_snapshot=pf["configs_snapshot"],
        status="prepared",
        calibration_version=pf["calibration_version"],
        led_mapping_version=pf["led_mapping_version"],
        configuration_version=pf["configuration_version"],
        physical_duration_seconds=pf["physical_duration_seconds"],
        operator_admin_id=operator_admin_id,
    )
    db.add(run)
    db.flush()

    codex_repo.append_hardware_event(
        db,
        hardware_run_id=run.hardware_run_id,
        controller_key=None,
        event_type="RUN_PREPARED",
        severity="info" if pf["ready_to_execute"] else "warning",
        message=(
            "CODEX run prepared cleanly (ready for explicit execution confirmation)."
            if pf["ready_to_execute"]
            else f"CODEX run prepared with {len(pf['blockers'])} pre-flight blocker(s)."
        ),
        payload={"blockers": pf["blockers"], "execution_mode": prepared_blob["execution_mode"]},
    )
    db.commit()
    db.refresh(run)

    return {
        "hardware_run_id": run.hardware_run_id,
        "simulation_id": sim.simulation_id,
        "site_id": site.site_id,
        "site_name": site.site_name,
        "execution_mode": prepared_blob["execution_mode"],
        "status": run.status,
        "ready_to_execute": pf["ready_to_execute"],
        "simulation_duration_seconds": int(sim.duration_seconds),
        "playback_speed": float(sim.playback_speed or 1.0),
        "physical_duration_seconds": pf["physical_duration_seconds"],
        "kepler_reference": pf["kepler_reference"],
        "orbital_targets_deg": pf["orbital_targets_deg"],
        "motor_plans": pf["motor_plans"],
        "moon_led_plan": pf["moon_led_plan"],
        "preflight_passed_count": pf["passed_count"],
        "preflight_total_steps": pf["total_steps"],
        "preflight_steps": pf["steps"],
        "blockers": pf["blockers"],
        "warnings": pf["warnings"],
        "actuation_performed": False,
        "created_at": sim.created_at,
    }


def _serialize_run_status(db: Session, run: HardwareRun) -> dict[str, Any]:
    acks = codex_repo.list_command_acknowledgements(db, run.hardware_run_id)
    return {
        "hardware_run_id": run.hardware_run_id,
        "simulation_id": run.simulation_id,
        "site_id": run.site_id,
        "status": run.status,
        "command_id": run.command_id,
        "calibration_version": run.calibration_version,
        "led_mapping_version": run.led_mapping_version,
        "configuration_version": run.configuration_version,
        "physical_duration_seconds": run.physical_duration_seconds,
        "operator_admin_id": run.operator_admin_id,
        "operator_confirmed_at": run.operator_confirmed_at,
        "idempotency_key": run.idempotency_key,
        "failure_reason": run.failure_reason,
        "upload_started_at": run.upload_started_at,
        "upload_acknowledged_at": run.upload_acknowledged_at,
        "execution_started_at": run.execution_started_at,
        "execution_finished_at": run.execution_finished_at,
        "estop_triggered_at": run.estop_triggered_at,
        "prepared_payload": redact_sensitive_mapping(run.prepared_payload or {}),
        "acknowledgements": [
            {
                "controller_key": a.controller_key,
                "ack_status": a.ack_status,
                "device_sequence": a.device_sequence,
                "message": a.message,
                "received_at": a.received_at,
            }
            for a in acks
        ],
    }


def execute_codex_run(
    db: Session,
    *,
    payload: dict[str, Any],
    operator_admin_id: UUID,
    transport: CodexTransport | None = None,
) -> dict[str, Any]:
    """Execute a prepared CODEX run strictly after explicit confirmation and 16-step verification."""
    if payload.get("confirmed") is not True:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Explicit operator confirmation (confirmed=true) is mandatory to actuate CODEX hardware.",
        )

    idempotency_key: str = payload["idempotency_key"].strip()
    existing_run = codex_repo.get_hardware_run_by_idempotency(db, idempotency_key)
    if existing_run is not None:
        if existing_run.hardware_run_id != payload["hardware_run_id"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="idempotency_key already belongs to a different hardware run.",
            )
        return _serialize_run_status(db, existing_run)

    run = codex_repo.get_hardware_run(db, payload["hardware_run_id"])
    if run is None or run.simulation_id is None or run.site_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prepared hardware run {payload['hardware_run_id']} not found.",
        )
    if run.status != "prepared":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Hardware run is in state '{run.status}' and cannot be re-executed without a new prepare.",
        )

    prepared_blob = dict(run.prepared_payload or {})
    mode = payload.get("execution_mode") or prepared_blob.get("execution_mode", "full_codex")

    # Strict live re-validation (allow_unverified_preview=False)
    pf = _evaluate_16_step_preflight(
        db,
        execution_mode=mode,
        physical_duration_seconds=run.physical_duration_seconds,
        clamp_to_travel_limits=False,
        allow_unverified_preview=False,
        allow_centroid_led_fallback=False,
        site_id=run.site_id,
        simulation_id=run.simulation_id,
        require_confirmed=True,
        confirmed=True,
    )
    if not pf["ready_to_execute"]:
        codex_repo.append_hardware_event(
            db,
            hardware_run_id=run.hardware_run_id,
            controller_key=None,
            event_type="RUN_BLOCKED_PREFLIGHT",
            severity="error",
            message="Hardware execution blocked by 16-step safety pre-flight.",
            payload={"blockers": pf["blockers"]},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "CODEX 16-step pre-flight check failed.",
                "blockers": pf["blockers"],
            },
        )

    now = codex_repo.utc_now()
    command_id = uuid.uuid4()
    seq = codex_repo.next_command_sequence(db)
    nonce = generate_command_nonce()
    dispatch_targets = ["moon_led_s3"] if mode == "led_only" else ["wifi_bridge", "moon_led_s3"]

    cmd_payload = build_codex_command_payload(
        command_id=str(command_id),
        simulation_id=str(run.simulation_id),
        site_id=run.site_id,
        sequence_number=seq,
        ttl_seconds=settings.CODEX_COMMAND_TTL_SECONDS,
        device_targets=pf["target_controllers"],
        configuration_version=pf["configuration_version"],
        calibration_version=pf["calibration_version"],
        led_mapping_version=pf["led_mapping_version"],
        motor_commands=pf["motor_plans"] if mode != "led_only" else None,
        moon_led=pf["moon_led_plan"],
        idempotency_key=idempotency_key,
        nonce=nonce,
        issued_at_utc=now,
    )
    signed_headers = build_signed_headers(settings.CODEX_SHARED_SECRET, cmd_payload)
    payload_sha = compute_payload_sha256(cmd_payload)

    uart_frame: bytes | None = None
    if mode != "led_only" and pf["motor_plans"] is not None:
        uart_bytes = encode_uno_motion_payload(
            nema17_plan=pf["motor_plans"].get("nema17"),
            byj_plan=pf["motor_plans"].get("byj"),
            physical_duration_seconds=pf["physical_duration_seconds"],
        )
        uart_frame = encode_uno_uart_frame(UART_MSG_MOTION_CMD, seq, uart_bytes)

    # Record replay-protection nonce entry & transition run/devices to busy
    expires_at = codex_repo.utc_now().fromisoformat(cmd_payload["expires_at_utc"])
    nonce_row = CodexCommandNonce(
        command_id=command_id,
        hardware_run_id=run.hardware_run_id,
        idempotency_key=idempotency_key,
        nonce=nonce,
        sequence_number=seq,
        target_devices=pf["target_controllers"],
        payload_sha256=payload_sha,
        issued_at_utc=now,
        expires_at_utc=expires_at,
        status="dispatched",
    )
    db.add(nonce_row)

    run.command_id = command_id
    run.idempotency_key = idempotency_key
    run.operator_admin_id = operator_admin_id
    run.operator_confirmed_at = now
    run.upload_started_at = now
    run.execution_started_at = now
    run.status = "dispatched"
    run.prepared_payload = {
        **prepared_blob,
        "execution_mode": mode,
        "motor_plans": pf["motor_plans"],
        "moon_led_plan": pf["moon_led_plan"],
        "command_id": str(command_id),
        "sequence_number": seq,
        "payload_sha256": payload_sha,
    }

    devices = {d.controller_key: d for d in codex_repo.list_hardware_devices(db)}
    for tk in pf["target_controllers"]:
        if tk in devices:
            devices[tk].health_state = "busy"
    db.flush()

    active_transport = transport or get_codex_transport()
    acks = []
    for target in dispatch_targets:
        dev = devices[target]
        ack = active_transport.dispatch_command(
            controller_key=target,
            endpoint_host=dev.endpoint_host,
            endpoint_port=dev.endpoint_port,
            command_payload=cmd_payload,
            signed_headers=signed_headers,
            uart_frame=uart_frame if target == "wifi_bridge" else None,
        )
        acks.append(ack)
        codex_repo.record_command_acknowledgement(
            db,
            hardware_run_id=run.hardware_run_id,
            command_id=command_id,
            controller_key=target,
            ack_status=ack.ack_status,
            device_sequence=ack.device_sequence,
            message=ack.message,
            telemetry=redact_sensitive_mapping(ack.telemetry),
        )

        # If wifi_bridge relayed UART to motion_uno, update motion_uno state cleanly too
        affected = ["wifi_bridge", "motion_uno"] if target == "wifi_bridge" else [target]
        for ck in affected:
            if ck not in devices:
                continue
            if ack.ack_status in ("accepted", "started", "completed"):
                devices[ck].health_state = "completed"
                devices[ck].last_error_code = None
                devices[ck].last_error_message = None
            elif ack.ack_status == "estopped":
                devices[ck].estop_latched = True
                devices[ck].health_state = "fault"
                devices[ck].last_error_code = "estop"
                devices[ck].last_error_message = ack.message
            else:
                devices[ck].health_state = "fault"
                devices[ck].last_error_code = f"ack_{ack.ack_status}"
                devices[ck].last_error_message = ack.message

    all_ok = all(a.ack_status in ("accepted", "started", "completed") for a in acks)
    any_ok = any(a.ack_status in ("accepted", "started", "completed") for a in acks)
    finished = codex_repo.utc_now()
    run.upload_acknowledged_at = finished
    run.execution_finished_at = finished

    if all_ok:
        run.status = "completed"
        nonce_row.status = "completed"
        codex_repo.append_hardware_event(
            db,
            hardware_run_id=run.hardware_run_id,
            controller_key=None,
            event_type="RUN_COMPLETED",
            severity="info",
            message=f"All target controllers ({dispatch_targets}) completed CODEX command.",
        )
    else:
        run.status = "partial_fault" if any_ok else "failed"
        nonce_row.status = "faulted"
        failures = [
            f"{a.controller_key}: {a.ack_status} ({a.message})"
            for a in acks
            if a.ack_status not in ("accepted", "started", "completed")
        ]
        run.failure_reason = "; ".join(failures)
        codex_repo.append_hardware_event(
            db,
            hardware_run_id=run.hardware_run_id,
            controller_key=None,
            event_type="RUN_FAULT",
            severity="error",
            message=run.failure_reason,
            payload={"failures": failures},
        )

    log_audit(
        db,
        action_key="CODEX_RUN_EXECUTE",
        entity_type="hardware_run",
        entity_id=str(run.hardware_run_id),
        admin_id=str(operator_admin_id),
        after_snapshot={
            "status": run.status,
            "execution_mode": mode,
            "command_id": str(command_id),
            "sequence_number": seq,
        },
    )
    db.commit()
    db.refresh(run)
    return _serialize_run_status(db, run)


def get_hardware_run_status(db: Session, hardware_run_id: UUID) -> dict[str, Any]:
    """Return full status and per-controller acknowledgements for a hardware run."""
    run = codex_repo.get_hardware_run(db, hardware_run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hardware run {hardware_run_id} not found.",
        )
    return _serialize_run_status(db, run)


def get_hardware_run_events(db: Session, hardware_run_id: UUID) -> dict[str, Any]:
    """Return ordered telemetry/audit events for a hardware run."""
    run = codex_repo.get_hardware_run(db, hardware_run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hardware run {hardware_run_id} not found.",
        )
    events = codex_repo.list_hardware_events(db, hardware_run_id)
    return {
        "hardware_run_id": run.hardware_run_id,
        "status": run.status,
        "events": [
            {
                "event_id": e.event_id,
                "controller_key": e.controller_key,
                "event_type": e.event_type,
                "severity": e.severity,
                "message": e.message,
                "payload": redact_sensitive_mapping(e.payload)
                if isinstance(e.payload, dict)
                else e.payload,
                "event_time": e.event_time,
            }
            for e in events
        ],
    }


def trigger_codex_estop(
    db: Session,
    *,
    reason: str,
    hardware_run_id: UUID | None,
    operator_admin_id: UUID,
    transport: CodexTransport | None = None,
) -> dict[str, Any]:
    """Issue highest-priority E-STOP across all CODEX controllers and latch fault state."""
    now = codex_repo.utc_now()
    seq = codex_repo.next_command_sequence(db)
    cmd_id = uuid.uuid4()
    nonce = generate_command_nonce()
    estop_payload = build_codex_command_payload(
        command_id=str(cmd_id),
        simulation_id=str(uuid.UUID(int=0)),
        site_id=0,
        sequence_number=seq,
        ttl_seconds=60,
        device_targets=list(ALL_CONTROLLER_KEYS),
        configuration_version="emergency_stop",
        calibration_version=None,
        led_mapping_version=None,
        motor_commands={"action": "ESTOP", "reason": reason},
        moon_led={"action": "OFF"},
        nonce=nonce,
        issued_at_utc=now,
    )
    signed_headers = build_signed_headers(settings.CODEX_SHARED_SECRET, estop_payload)
    uart_frame = encode_uno_uart_frame(UART_MSG_ESTOP, seq, b"ESTOP!")

    nonce_row = CodexCommandNonce(
        command_id=cmd_id,
        hardware_run_id=hardware_run_id,
        idempotency_key=f"estop-{cmd_id}",
        nonce=nonce,
        sequence_number=seq,
        target_devices=list(ALL_CONTROLLER_KEYS),
        payload_sha256=compute_payload_sha256(estop_payload),
        issued_at_utc=now,
        expires_at_utc=now.fromisoformat(estop_payload["expires_at_utc"]),
        status="aborted",
    )
    db.add(nonce_row)

    active_transport = transport or get_codex_transport()
    devices = {d.controller_key: d for d in codex_repo.list_hardware_devices(db)}
    ctrl_acks: list[dict[str, Any]] = []

    for target in ("wifi_bridge", "moon_led_s3"):
        dev = devices.get(target)
        ack = active_transport.dispatch_estop(
            controller_key=target,
            endpoint_host=dev.endpoint_host if dev else None,
            endpoint_port=dev.endpoint_port if dev else None,
            command_payload=estop_payload,
            signed_headers=signed_headers,
            uart_frame=uart_frame if target == "wifi_bridge" else None,
        )
        ctrl_acks.append(
            {
                "controller_key": target,
                "ack_status": ack.ack_status,
                "message": ack.message,
            }
        )

    for dev in devices.values():
        dev.estop_latched = True
        dev.health_state = "fault"
        dev.last_error_code = "estop"
        dev.last_error_message = f"E-STOP latched: {reason}"

    runs_to_abort = codex_repo.list_active_hardware_runs(db)
    if hardware_run_id is not None:
        explicit = codex_repo.get_hardware_run(db, hardware_run_id)
        if explicit is not None and all(
            r.hardware_run_id != explicit.hardware_run_id for r in runs_to_abort
        ):
            runs_to_abort.append(explicit)

    aborted_ids: list[UUID] = []
    for r in runs_to_abort:
        r.status = "estopped"
        r.estop_triggered_at = now
        r.execution_finished_at = now
        r.failure_reason = f"Aborted by operator E-STOP: {reason}"
        aborted_ids.append(r.hardware_run_id)
        codex_repo.append_hardware_event(
            db,
            hardware_run_id=r.hardware_run_id,
            controller_key=None,
            event_type="ESTOP_TRIGGERED",
            severity="critical",
            message=reason,
            payload={"controller_acknowledgements": ctrl_acks},
        )

    log_audit(
        db,
        action_key="CODEX_ESTOP",
        entity_type="codex_system",
        entity_id=",".join(str(x) for x in aborted_ids) or "bench",
        admin_id=str(operator_admin_id),
        after_snapshot={"reason": reason, "aborted_run_count": len(aborted_ids)},
    )
    db.commit()
    return {
        "estop_latched": True,
        "triggered_at": now,
        "aborted_run_ids": aborted_ids,
        "controller_acknowledgements": ctrl_acks,
    }


def create_code_version(
    db: Session,
    *,
    payload: dict[str, Any],
    admin_id: UUID,
) -> dict[str, Any]:
    """Create an immutable firmware template version with allow-listed placeholders."""
    existing = codex_repo.get_code_version_by_label(
        db, payload["controller_key"], payload["version_label"]
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Firmware version '{payload['version_label']}' already exists for "
                f"controller '{payload['controller_key']}'."
            ),
        )

    source_code = payload["source_code"]
    checksum = compute_sha256_hex(source_code)
    placeholders = [dict(p) for p in payload.get("placeholders", [])]

    declared: set[str] = set()
    for p in placeholders:
        key = p["placeholder_key"]
        if key in declared:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Duplicate placeholder_key '{key}' in placeholders list.",
            )
        declared.add(key)

    if source_code.count("{{") != source_code.count("}}"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed template braces: unmatched '{{' or '}}' detected in source_code.",
        )

    for m in RAW_TOKEN_PATTERN.finditer(source_code):
        tok = m.group(1)
        if not re.fullmatch(r"[A-Z0-9_]{2,64}", tok):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Malformed template placeholder '{{{{{tok}}}}}'. Keys must match "
                    "^[A-Z0-9_]{2,64}$."
                ),
            )
        if tok not in declared:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Undeclared template placeholder '{{{{{tok}}}}}' must be added to "
                    "placeholders list."
                ),
            )

    cv = codex_repo.create_code_version_with_placeholders(
        db,
        controller_key=payload["controller_key"],
        version_label=payload["version_label"],
        source_code=source_code,
        language=payload.get("language", "cpp"),
        board_target=payload["board_target"],
        checksum=checksum,
        library_manifest=payload.get("library_manifest"),
        created_by_admin_id=admin_id,
        notes=payload.get("notes"),
        placeholders=placeholders,
        activate=bool(payload.get("activate", True)),
    )
    log_audit(
        db,
        action_key="CODEX_CODE_VERSION_CREATE",
        entity_type="hardware_code_version",
        entity_id=str(cv.code_version_id),
        admin_id=str(admin_id),
        after_snapshot={
            "controller_key": cv.controller_key,
            "version_label": cv.version_label,
            "checksum": cv.checksum,
            "is_active": bool(cv.is_active),
        },
    )
    db.commit()
    db.refresh(cv)
    return serialize_code_version(db, cv, include_source=True)


def serialize_code_version(db: Session, cv: Any, *, include_source: bool = False) -> dict[str, Any]:
    """Serialize HardwareCodeVersion and its CodePlaceholder definitions cleanly."""
    ph_rows = codex_repo.list_placeholders_for_version(db, cv.code_version_id)
    payload: dict[str, Any] = {
        "code_version_id": cv.code_version_id,
        "controller_key": cv.controller_key,
        "version_label": cv.version_label,
        "language": cv.language,
        "board_target": cv.board_target,
        "checksum": cv.checksum,
        "library_manifest": cv.library_manifest,
        "is_active": bool(cv.is_active),
        "notes": cv.notes,
        "created_at": cv.created_at,
        "placeholders": [
            {
                "placeholder_id": p.placeholder_id,
                "placeholder_key": p.placeholder_key,
                "description": p.description,
                "data_type": p.data_type,
                "unit": p.unit,
                "required": p.required,
                "default_value": p.default_value,
                "validation_schema": p.validation_schema,
                "injection_format": p.injection_format,
                "order_index": p.order_index,
            }
            for p in ph_rows
        ],
    }
    if include_source:
        builds = codex_repo.list_firmware_builds(db, code_version_id=cv.code_version_id)
        payload["source_code"] = cv.source_code
        payload["created_by_admin_id"] = cv.created_by_admin_id
        payload["builds"] = [
            {
                "build_id": str(b.build_id),
                "build_target": getattr(b, "build_target", cv.board_target),
                "toolchain_version": getattr(b, "toolchain_version", None),
                "build_status": getattr(b, "build_status", None),
                "binary_checksum": getattr(b, "binary_checksum", None),
                "created_at": b.created_at.isoformat() if getattr(b, "created_at", None) else None,
            }
            for b in builds
        ]
    return payload


def get_code_version_detail(db: Session, code_version_id: UUID) -> dict[str, Any]:
    """Return full immutable firmware source code, checksum, placeholders, and build history."""
    cv = codex_repo.get_code_version(db, code_version_id)
    if cv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hardware code version {code_version_id} not found.",
        )
    return serialize_code_version(db, cv, include_source=True)


def activate_code_version(
    db: Session,
    *,
    code_version_id: UUID,
    admin_id: UUID,
) -> dict[str, Any]:
    """Promote an immutable firmware code version as active for its controller without flashing."""
    cv = codex_repo.get_code_version(db, code_version_id)
    if cv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hardware code version {code_version_id} not found.",
        )
    previously_active = [
        str(row.code_version_id)
        for row in codex_repo.list_code_versions(db, controller_key=cv.controller_key)
        if row.is_active and row.code_version_id != cv.code_version_id
    ]
    codex_repo.activate_code_version(db, cv)
    log_audit(
        db,
        action_key="CODEX_CODE_VERSION_ACTIVATE",
        entity_type="hardware_code_version",
        entity_id=str(cv.code_version_id),
        admin_id=str(admin_id),
        before_snapshot={"deactivated_version_ids": previously_active},
        after_snapshot={
            "controller_key": cv.controller_key,
            "version_label": cv.version_label,
            "is_active": True,
        },
    )
    db.commit()
    db.refresh(cv)
    return serialize_code_version(db, cv, include_source=True)


def compare_code_versions(
    db: Session,
    *,
    base_version_id: UUID,
    target_version_id: UUID,
) -> dict[str, Any]:
    """Compute a deterministic unified diff and placeholder diff between two firmware versions."""
    base_cv = codex_repo.get_code_version(db, base_version_id)
    target_cv = codex_repo.get_code_version(db, target_version_id)
    if base_cv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Base firmware version {base_version_id} not found.",
        )
    if target_cv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target firmware version {target_version_id} not found.",
        )
    if base_cv.controller_key != target_cv.controller_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot diff across controllers ('{base_cv.controller_key}' vs "
                f"'{target_cv.controller_key}')."
            ),
        )

    diff_lines = list(
        difflib.unified_diff(
            base_cv.source_code.splitlines(),
            target_cv.source_code.splitlines(),
            fromfile=f"{base_cv.controller_key}:{base_cv.version_label}",
            tofile=f"{target_cv.controller_key}:{target_cv.version_label}",
            lineterm="",
        )
    )
    added = sum(1 for ln in diff_lines if ln.startswith("+") and not ln.startswith("+++"))
    removed = sum(1 for ln in diff_lines if ln.startswith("-") and not ln.startswith("---"))

    base_ph = {
        p.placeholder_key: p
        for p in codex_repo.list_placeholders_for_version(db, base_cv.code_version_id)
    }
    target_ph = {
        p.placeholder_key: p
        for p in codex_repo.list_placeholders_for_version(db, target_cv.code_version_id)
    }
    placeholder_changes: list[dict[str, Any]] = []
    for key in sorted(set(base_ph) | set(target_ph)):
        b_item = base_ph.get(key)
        t_item = target_ph.get(key)
        if b_item is None and t_item is not None:
            placeholder_changes.append(
                {"key": key, "change": "added", "data_type": t_item.data_type}
            )
        elif t_item is None and b_item is not None:
            placeholder_changes.append(
                {"key": key, "change": "removed", "data_type": b_item.data_type}
            )
        elif (
            b_item is not None
            and t_item is not None
            and (
                b_item.data_type != t_item.data_type
                or b_item.default_value != t_item.default_value
                or b_item.injection_format != t_item.injection_format
            )
        ):
            placeholder_changes.append(
                {
                    "key": key,
                    "change": "modified",
                    "from_type": b_item.data_type,
                    "to_type": t_item.data_type,
                }
            )

    return {
        "base_version_id": base_cv.code_version_id,
        "target_version_id": target_cv.code_version_id,
        "controller_key": target_cv.controller_key,
        "base_version_label": base_cv.version_label,
        "target_version_label": target_cv.version_label,
        "unified_diff": "\n".join(diff_lines),
        "added_lines": added,
        "removed_lines": removed,
        "placeholder_changes": placeholder_changes,
    }


def _strip_cpp_strings_and_comments(source: str) -> str:
    """Strip C/C++ comments and string literals for balanced delimiter static checks."""
    out: list[str] = []
    i = 0
    n = len(source)
    in_line_comment = False
    in_block_comment = False
    in_string: str | None = None
    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                out.append(ch)
        elif in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 1
        elif in_string is not None:
            if ch == "\\" and i + 1 < n:
                i += 1
            elif ch == in_string:
                in_string = None
        else:
            if ch == "/" and nxt == "/":
                in_line_comment = True
                i += 1
            elif ch == "/" and nxt == "*":
                in_block_comment = True
                i += 1
            elif ch in ('"', "'"):
                in_string = ch
            else:
                out.append(ch)
        i += 1
    return "".join(out)


def validate_code_version_syntax(db: Session, *, code_version_id: UUID) -> dict[str, Any]:
    """Run deterministic non-actuating static, brace, safety-guard, and placeholder checks."""
    cv = codex_repo.get_code_version(db, code_version_id)
    if cv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hardware code version {code_version_id} not found.",
        )

    ph_rows = codex_repo.list_placeholders_for_version(db, cv.code_version_id)
    declared = {p.placeholder_key for p in ph_rows}
    errors: list[str] = []
    warnings: list[str] = []
    undeclared_tokens: list[str] = []
    malformed_tokens: list[str] = []

    if cv.source_code.count("{{") != cv.source_code.count("}}"):
        errors.append("Unmatched '{{' or '}}' template delimiter pair detected.")

    for m in RAW_TOKEN_PATTERN.finditer(cv.source_code):
        tok = m.group(1)
        if not re.fullmatch(r"[A-Z0-9_]{2,64}", tok):
            if tok not in malformed_tokens:
                malformed_tokens.append(tok)
        elif tok not in declared and tok not in undeclared_tokens:
            undeclared_tokens.append(tok)

    if malformed_tokens:
        errors.append(f"Malformed placeholder keys: {', '.join(malformed_tokens)}")
    if undeclared_tokens:
        errors.append(f"Undeclared placeholder keys: {', '.join(undeclared_tokens)}")

    stripped = _strip_cpp_strings_and_comments(cv.source_code)
    pairs = {"{": "}", "(": ")", "[": "]"}
    closing = {"}": "{", ")": "(", "]": "["}
    stack: list[str] = []
    for ch in stripped:
        if ch in pairs:
            stack.append(ch)
        elif ch in closing:
            if not stack or stack[-1] != closing[ch]:
                errors.append(f"Unbalanced C/C++ delimiter near '{ch}'.")
                break
            stack.pop()
    if stack and not errors:
        errors.append(f"Unclosed C/C++ delimiter(s): {' '.join(stack)}")

    if "void setup(" not in cv.source_code or "void loop(" not in cv.source_code:
        warnings.append("Sketch does not define standard Arduino 'setup()' and 'loop()' functions.")
    if '#error "SAFETY BLOCK:' in cv.source_code:
        warnings.append(
            "Sketch preserves Phase 5 '#error SAFETY BLOCK' guard until hardware verification."
        )

    arduino_cli = shutil.which("arduino-cli")
    pio = shutil.which("pio")
    toolchain_available = bool(arduino_cli or pio)
    if toolchain_available:
        toolchain_note = (
            "External microcontroller toolchain binary detected on host; this endpoint performs "
            "static placeholder/delimiter verification only and never flashes devices."
        )
    else:
        toolchain_note = (
            "Host has no arduino-cli or PlatformIO toolchain installed; full cross-compilation "
            "requires external Arduino/PlatformIO build host or Hardware Team bench environment."
        )

    return {
        "code_version_id": cv.code_version_id,
        "controller_key": cv.controller_key,
        "board_target": cv.board_target,
        "valid_static_checks": len(errors) == 0,
        "toolchain_available": toolchain_available,
        "toolchain_note": toolchain_note,
        "undeclared_tokens": undeclared_tokens,
        "malformed_tokens": malformed_tokens,
        "warnings": warnings,
        "errors": errors,
    }


def list_hardware_variables_catalog(db: Session) -> list[dict[str, Any]]:
    """Build live PostgreSQL-driven variable reference catalog for Firmware Editor split pane."""
    devices = codex_repo.list_hardware_devices(db)
    configs = codex_repo.list_active_configurations(db)
    calibrations = codex_repo.list_motor_calibrations(db, active_only=True)
    regions = codex_repo.list_moon_led_regions(db)
    active_code = codex_repo.list_active_code_versions(db)

    cal_by_motor = {c.motor_key: c for c in calibrations if c.motor_key}
    cfg_by_controller = {c.controller_key: c for c in configs}
    dev_by_controller = {d.controller_key: d for d in devices}
    code_by_controller = {v.controller_key: v for v in active_code}

    verified_regions = [r for r in regions if r.verification_status == "bench_verified"]
    nema = cal_by_motor.get("nema17")
    byj = cal_by_motor.get("byj")
    uno_cfg = cfg_by_controller.get("motion_uno")
    s3_cfg = cfg_by_controller.get("moon_led_s3")
    wifi_dev = dev_by_controller.get("wifi_bridge")

    variables: list[dict[str, Any]] = [
        {
            "key": "CODEX_TRANSPORT_MODE",
            "category": "transport",
            "source_table": "settings",
            "description": "Active CODEX transport adapter mode ('mock' vs 'http').",
            "data_type": "string",
            "unit": None,
            "current_value": settings.CODEX_TRANSPORT_MODE,
            "injection_format": "c_string",
            "example_placeholder": "{{CODEX_TRANSPORT_MODE}}",
        },
        {
            "key": "CODEX_MAX_PREPARE_STEPS",
            "category": "protocol",
            "source_table": "codex.protocol",
            "description": "Signed codex.v1 frame sequence & HMAC-SHA256 verification status.",
            "data_type": "string",
            "unit": None,
            "current_value": (
                f"wifi_bridge={wifi_dev.health_state if wifi_dev else 'unregistered'} / "
                f"verify={wifi_dev.verification_status if wifi_dev else 'unregistered'}"
            ),
            "injection_format": "c_string",
            "example_placeholder": "{{CODEX_PROTOCOL_STATE}}",
        },
        {
            "key": "NEMA17_STEPS_PER_REV",
            "category": "kinematics",
            "source_table": "motor_calibration_profiles",
            "description": "Measured NEMA17 full steps per revolution (null until bench verified).",
            "data_type": "int",
            "unit": "steps/rev",
            "current_value": (
                nema.full_steps_per_rev
                if nema and nema.verification_status == "bench_verified"
                else None
            ),
            "injection_format": "cpp_literal",
            "example_placeholder": "{{NEMA17_STEPS_PER_REV}}",
        },
        {
            "key": "NEMA17_MICROSTEPS",
            "category": "kinematics",
            "source_table": "motor_calibration_profiles",
            "description": "Measured NEMA17 microstepping factor (null until bench verified).",
            "data_type": "int",
            "unit": "microsteps",
            "current_value": (
                nema.microsteps if nema and nema.verification_status == "bench_verified" else None
            ),
            "injection_format": "cpp_literal",
            "example_placeholder": "{{NEMA17_MICROSTEPS}}",
        },
        {
            "key": "NEMA17_GEAR_RATIO",
            "category": "kinematics",
            "source_table": "motor_calibration_profiles",
            "description": "Measured NEMA17 gear reduction ratio (null until bench verified).",
            "data_type": "float",
            "unit": "ratio",
            "current_value": (
                nema.gear_reduction_ratio
                if nema and nema.verification_status == "bench_verified"
                else None
            ),
            "injection_format": "cpp_literal",
            "example_placeholder": "{{NEMA17_GEAR_RATIO}}",
        },
        {
            "key": "NEMA17_MAX_STEP_RATE",
            "category": "kinematics",
            "source_table": "motor_calibration_profiles",
            "description": "Safe maximum NEMA17 step rate (steps/sec, null until bench verified).",
            "data_type": "int",
            "unit": "steps/s",
            "current_value": (
                nema.max_step_rate
                if nema and nema.verification_status == "bench_verified"
                else None
            ),
            "injection_format": "cpp_literal",
            "example_placeholder": "{{NEMA17_MAX_STEP_RATE}}",
        },
        {
            "key": "BYJ_STEPS_PER_REV",
            "category": "kinematics",
            "source_table": "motor_calibration_profiles",
            "description": "Measured BYJ stepper full steps per revolution (null until verified).",
            "data_type": "int",
            "unit": "steps/rev",
            "current_value": (
                byj.full_steps_per_rev
                if byj and byj.verification_status == "bench_verified"
                else None
            ),
            "injection_format": "cpp_literal",
            "example_placeholder": "{{BYJ_STEPS_PER_REV}}",
        },
        {
            "key": "BYJ_GEAR_RATIO",
            "category": "kinematics",
            "source_table": "motor_calibration_profiles",
            "description": "Measured BYJ stepper gear ratio (null until bench verified).",
            "data_type": "float",
            "unit": "ratio",
            "current_value": (
                byj.gear_reduction_ratio
                if byj and byj.verification_status == "bench_verified"
                else None
            ),
            "injection_format": "cpp_literal",
            "example_placeholder": "{{BYJ_GEAR_RATIO}}",
        },
        {
            "key": "MOTION_UNO_TARGET_BOARD",
            "category": "controller",
            "source_table": "hardware_configurations",
            "description": "Active motion_uno board target FQBN and active code version.",
            "data_type": "string",
            "unit": None,
            "current_value": (
                code_by_controller["motion_uno"].version_label
                if "motion_uno" in code_by_controller
                else (uno_cfg.firmware_target if uno_cfg else None)
            ),
            "injection_format": "c_string",
            "example_placeholder": "{{MOTION_UNO_TARGET_BOARD}}",
        },
        {
            "key": "MOON_LED_COUNT",
            "category": "led_mapping",
            "source_table": "hardware_configurations",
            "description": "Configured physical Moon LED count (null until bench verified).",
            "data_type": "int",
            "unit": "pixels",
            "current_value": s3_cfg.led_count if s3_cfg else None,
            "injection_format": "cpp_literal",
            "example_placeholder": "{{MOON_LED_COUNT}}",
        },
        {
            "key": "MOON_LED_VERIFIED_REGIONS",
            "category": "led_mapping",
            "source_table": "moon_led_regions",
            "description": "Count of bench-verified spherical Moon regions out of 13.",
            "data_type": "int",
            "unit": "regions",
            "current_value": f"{len(verified_regions)}/{len(regions)} bench_verified",
            "injection_format": "cpp_literal",
            "example_placeholder": "{{MOON_LED_VERIFIED_REGIONS}}",
        },
    ]

    seen_keys = {item["key"] for item in variables}
    for cv in active_code:
        for ph in codex_repo.list_placeholders_for_version(db, cv.code_version_id):
            if ph.placeholder_key in seen_keys:
                continue
            seen_keys.add(ph.placeholder_key)
            variables.append(
                {
                    "key": ph.placeholder_key,
                    "category": f"template:{cv.controller_key}",
                    "source_table": "code_placeholders",
                    "description": ph.description or f"Placeholder from {cv.version_label}",
                    "data_type": ph.data_type,
                    "unit": ph.unit,
                    "current_value": ph.default_value,
                    "injection_format": ph.injection_format or "cpp_literal",
                    "example_placeholder": f"{{{{{ph.placeholder_key}}}}}",
                }
            )
    return variables


def list_hardware_configurations_admin(
    db: Session, *, controller_key: str | None = None
) -> list[dict[str, Any]]:
    """Serialize all stored HardwareConfiguration baselines for admin inspection."""
    rows = codex_repo.list_hardware_configurations(db, controller_key=controller_key)
    return [
        {
            "hardware_config_id": r.hardware_config_id,
            "controller_key": r.controller_key,
            "board_model": r.board_model,
            "firmware_target": r.firmware_target,
            "motor_type": r.motor_type,
            "steps_per_revolution": r.steps_per_revolution,
            "microstep_setting": r.microstep_setting,
            "gear_ratio": r.gear_ratio,
            "driver_model": r.driver_model,
            "current_limit_setting": r.current_limit_setting,
            "led_count": r.led_count,
            "led_mapping_version": r.led_mapping_version,
            "config_json": r.config_json,
            "is_active": bool(r.is_active),
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


def list_hardware_runs_admin(
    db: Session,
    *,
    status_filter: str | None = None,
    site_id: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Serialize CODEX hardware run history for administrative auditing."""
    runs = codex_repo.list_hardware_runs(
        db,
        status_filter=status_filter,
        site_id=site_id,
        limit=limit,
    )
    return [
        {
            "hardware_run_id": r.hardware_run_id,
            "simulation_id": r.simulation_id,
            "site_id": r.site_id,
            "status": r.status,
            "start_time_utc": r.start_time_utc,
            "duration_seconds": r.duration_seconds,
            "physical_duration_seconds": r.physical_duration_seconds,
            "calibration_version": r.calibration_version,
            "led_mapping_version": r.led_mapping_version,
            "configuration_version": r.configuration_version,
            "operator_admin_id": r.operator_admin_id,
            "operator_confirmed_at": r.operator_confirmed_at,
            "execution_started_at": r.execution_started_at,
            "execution_finished_at": r.execution_finished_at,
            "estop_triggered_at": r.estop_triggered_at,
            "failure_reason": r.failure_reason,
        }
        for r in runs
    ]


def render_code_version_preview(
    db: Session,
    *,
    code_version_id: UUID,
    values: dict[str, Any],
) -> dict[str, Any]:
    """Render allow-listed template placeholders strictly for inspection without device upload."""
    cv = codex_repo.get_code_version(db, code_version_id)
    if cv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hardware code version {code_version_id} not found.",
        )
    ph_rows = codex_repo.list_placeholders_for_version(db, cv.code_version_id)
    specs = [
        PlaceholderSpec(
            placeholder_key=p.placeholder_key,
            data_type=p.data_type,
            required=p.required,
            default_value=p.default_value,
            validation_schema=p.validation_schema,
            injection_format=p.injection_format or "cpp_literal",
            unit=p.unit,
        )
        for p in ph_rows
    ]
    try:
        rendered = render_firmware_template(
            cv.source_code,
            specs,
            values,
            expected_source_checksum=cv.checksum,
        )
    except TemplateRenderError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    return {
        "code_version_id": str(cv.code_version_id),
        "controller_key": cv.controller_key,
        "version_label": cv.version_label,
        "source_checksum_sha256": rendered.source_checksum_sha256,
        "rendered_checksum_sha256": rendered.rendered_checksum_sha256,
        "substituted_keys": rendered.substituted_keys,
        "warnings": rendered.warnings,
        "rendered_source": rendered.rendered_source,
    }
