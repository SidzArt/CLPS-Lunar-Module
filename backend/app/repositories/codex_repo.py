"""Database repository operations for CODEX devices, calibrations, LEDs, firmware, and runs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.catalogue import LandingSite
from app.models.codex import (
    CodePlaceholder,
    CodexCommandNonce,
    HardwareCodeVersion,
    HardwareCommandAcknowledgement,
    HardwareConfiguration,
    HardwareDevice,
    HardwareEvent,
    HardwareRun,
    MoonLedRegion,
    MoonLedRegionPixel,
    MotorCalibrationProfile,
)
from app.models.operations import FirmwareBuild
from app.models.simulation import SimulationRun, SimulationSample


def list_hardware_devices(db: Session) -> list[HardwareDevice]:
    """Return all registered physical CODEX controllers ordered consistently."""
    return list(
        db.scalars(select(HardwareDevice).order_by(HardwareDevice.controller_key.asc())).all()
    )


def get_hardware_device(db: Session, controller_key: str) -> HardwareDevice | None:
    """Fetch a single physical CODEX controller record."""
    return db.scalar(select(HardwareDevice).where(HardwareDevice.controller_key == controller_key))


def list_active_configurations(db: Session) -> list[HardwareConfiguration]:
    """List active controller hardware configuration baselines."""
    return list(
        db.scalars(
            select(HardwareConfiguration)
            .where(HardwareConfiguration.is_active.is_(True))
            .order_by(HardwareConfiguration.controller_key.asc())
        ).all()
    )


def upsert_hardware_configuration(
    db: Session,
    *,
    controller_key: str,
    board_model: str,
    firmware_target: str,
    motor_type: str | None = None,
    steps_per_revolution: int | None = None,
    microstep_setting: int | None = None,
    gear_ratio: float | None = None,
    driver_model: str | None = None,
    current_limit_setting: str | None = None,
    led_count: int | None = None,
    led_mapping_version: str | None = None,
    config_json: dict[str, Any] | None = None,
) -> HardwareConfiguration:
    """Create or rotate an active controller hardware configuration baseline."""
    db.execute(
        update(HardwareConfiguration)
        .where(
            HardwareConfiguration.controller_key == controller_key,
            HardwareConfiguration.is_active.is_(True),
        )
        .values(is_active=False)
    )
    cfg = HardwareConfiguration(
        controller_key=controller_key,
        board_model=board_model,
        firmware_target=firmware_target,
        motor_type=motor_type,
        steps_per_revolution=steps_per_revolution,
        microstep_setting=microstep_setting,
        gear_ratio=gear_ratio,
        driver_model=driver_model,
        current_limit_setting=current_limit_setting,
        led_count=led_count,
        led_mapping_version=led_mapping_version,
        config_json=config_json,
        is_active=True,
    )
    db.add(cfg)
    db.flush()
    return cfg


def list_motor_calibrations(
    db: Session,
    *,
    motor_key: str | None = None,
    active_only: bool = False,
) -> list[MotorCalibrationProfile]:
    """List versioned motor calibration profiles ordered newest first."""
    stmt = select(MotorCalibrationProfile)
    if motor_key:
        stmt = stmt.where(MotorCalibrationProfile.motor_key == motor_key)
    if active_only:
        stmt = stmt.where(MotorCalibrationProfile.is_active.is_(True))
    stmt = stmt.order_by(MotorCalibrationProfile.calibration_id.desc())
    return list(db.scalars(stmt).all())


def get_motor_calibration_by_id(db: Session, calibration_id: int) -> MotorCalibrationProfile | None:
    """Retrieve a specific motor calibration profile version."""
    return db.get(MotorCalibrationProfile, calibration_id)


def get_active_motor_calibration(db: Session, motor_key: str) -> MotorCalibrationProfile | None:
    """Retrieve currently active calibration profile for a motor axis (`nema17` or `byj`)."""
    stmt = (
        select(MotorCalibrationProfile)
        .where(
            MotorCalibrationProfile.is_active.is_(True),
            (MotorCalibrationProfile.motor_key == motor_key)
            | (func.lower(MotorCalibrationProfile.motor_name).contains(motor_key.lower())),
        )
        .order_by(MotorCalibrationProfile.calibration_id.desc())
        .limit(1)
    )
    return db.scalar(stmt)


def create_versioned_motor_calibration(
    db: Session,
    *,
    payload: dict[str, Any],
    activate: bool = True,
) -> tuple[MotorCalibrationProfile, int | None]:
    """Insert a new motor calibration version cleanly without overwriting prior rows."""
    motor_key = payload.get("motor_key")
    prior_id: int | None = None
    if activate and motor_key:
        prior = get_active_motor_calibration(db, motor_key)
        if prior is not None:
            prior_id = prior.calibration_id
            prior.is_active = False
            if prior.verification_status == "bench_verified":
                prior.verification_status = "deprecated"

    row = MotorCalibrationProfile(
        **payload,
        supersedes_calibration_id=prior_id,
        is_active=activate,
    )
    db.add(row)
    db.flush()
    return row, prior_id


def list_moon_led_regions(db: Session, *, active_only: bool = True) -> list[MoonLedRegion]:
    """List 13-region Moon LED entries ordered by physical region index."""
    stmt = select(MoonLedRegion)
    if active_only:
        stmt = stmt.where(MoonLedRegion.is_active.is_(True))
    stmt = stmt.order_by(MoonLedRegion.region_index.asc())
    return list(db.scalars(stmt).all())


def get_moon_led_region_by_index(db: Session, region_index: int) -> MoonLedRegion | None:
    """Fetch a Moon LED region by its canonical 1..13 region index."""
    return db.scalar(select(MoonLedRegion).where(MoonLedRegion.region_index == region_index))


def list_moon_led_region_pixels(
    db: Session, region_id: int | None = None, *, active_only: bool = True
) -> list[MoonLedRegionPixel]:
    """List normalized physical LED/channel records for one or all regions."""
    stmt = select(MoonLedRegionPixel)
    if region_id is not None:
        stmt = stmt.where(MoonLedRegionPixel.region_id == region_id)
    if active_only:
        stmt = stmt.where(MoonLedRegionPixel.is_active.is_(True))
    stmt = stmt.order_by(MoonLedRegionPixel.region_id.asc(), MoonLedRegionPixel.pixel_order.asc())
    return list(db.scalars(stmt).all())


def upsert_moon_led_region_with_pixels(
    db: Session,
    *,
    region_index: int,
    region_name: str,
    centroid_lat: float | None,
    centroid_lon: float | None,
    boundary_polygon: Any | None,
    pixel_indices: list[int],
    mapping_version: str,
    orientation_reference: str | None,
    verification_status: str,
    geometry_source: str | None,
    output_channel: int | None = 0,
    topology_mode: str = "addressable_strip",
    is_active: bool = True,
) -> MoonLedRegion:
    """Create or update a Moon LED region (1..13) and synchronize active normalized pixel rows."""
    resolved_lat = float(centroid_lat) if centroid_lat is not None else 0.0
    resolved_lon = float(centroid_lon) if centroid_lon is not None else 0.0
    region = get_moon_led_region_by_index(db, region_index)
    if region is None:
        region = MoonLedRegion(
            region_index=region_index,
            region_name=region_name,
            centroid_lat=resolved_lat,
            centroid_lon=resolved_lon,
            boundary_polygon=boundary_polygon,
            pixel_indices=pixel_indices,
            mapping_version=mapping_version,
            orientation_reference=orientation_reference,
            verification_status=verification_status,
            geometry_source=geometry_source,
            is_active=is_active,
        )
        db.add(region)
        db.flush()
    else:
        region.region_name = region_name
        region.centroid_lat = resolved_lat
        region.centroid_lon = resolved_lon
        region.boundary_polygon = boundary_polygon
        region.pixel_indices = pixel_indices
        region.mapping_version = mapping_version
        region.orientation_reference = orientation_reference
        region.verification_status = verification_status
        region.geometry_source = geometry_source
        region.is_active = is_active
        db.flush()

    # Deactivate historical pixel rows for this region without dropping audit trail
    db.execute(
        update(MoonLedRegionPixel)
        .where(
            MoonLedRegionPixel.region_id == region.region_id,
            MoonLedRegionPixel.is_active.is_(True),
        )
        .values(is_active=False)
    )
    for order_idx, px in enumerate(pixel_indices):
        db.add(
            MoonLedRegionPixel(
                region_id=region.region_id,
                controller_key="moon_led_s3",
                mapping_version=mapping_version,
                output_channel=output_channel,
                pixel_index=px,
                pixel_order=order_idx,
                topology_mode=topology_mode,
                verification_status=(
                    "bench_verified" if verification_status == "bench_verified" else "unverified"
                ),
                is_active=True,
            )
        )
    db.flush()
    return region


def list_code_versions(
    db: Session, *, controller_key: str | None = None
) -> list[HardwareCodeVersion]:
    """List versioned controller firmware records ordered newest first."""
    stmt = select(HardwareCodeVersion)
    if controller_key:
        stmt = stmt.where(HardwareCodeVersion.controller_key == controller_key)
    stmt = stmt.order_by(HardwareCodeVersion.created_at.desc())
    return list(db.scalars(stmt).all())


def get_code_version(db: Session, code_version_id: uuid.UUID) -> HardwareCodeVersion | None:
    """Fetch a single firmware code version record."""
    return db.get(HardwareCodeVersion, code_version_id)


def get_code_version_by_label(
    db: Session, controller_key: str, version_label: str
) -> HardwareCodeVersion | None:
    """Check whether a controller already has a firmware version with the same label."""
    return db.scalar(
        select(HardwareCodeVersion).where(
            HardwareCodeVersion.controller_key == controller_key,
            HardwareCodeVersion.version_label == version_label,
        )
    )


def activate_code_version(db: Session, cv: HardwareCodeVersion) -> HardwareCodeVersion:
    """Activate an immutable firmware code version and deactivate siblings for its controller."""
    db.execute(
        update(HardwareCodeVersion)
        .where(
            HardwareCodeVersion.controller_key == cv.controller_key,
            HardwareCodeVersion.is_active.is_(True),
        )
        .values(is_active=False)
    )
    cv.is_active = True
    db.flush()
    return cv


def list_active_code_versions(db: Session) -> list[HardwareCodeVersion]:
    """List currently active firmware code versions ordered by controller key."""
    return list(
        db.scalars(
            select(HardwareCodeVersion)
            .where(HardwareCodeVersion.is_active.is_(True))
            .order_by(HardwareCodeVersion.controller_key.asc())
        ).all()
    )


def list_hardware_configurations(
    db: Session, *, controller_key: str | None = None
) -> list[HardwareConfiguration]:
    """List hardware configuration baselines ordered with active configs first."""
    stmt = select(HardwareConfiguration)
    if controller_key:
        stmt = stmt.where(HardwareConfiguration.controller_key == controller_key)
    stmt = stmt.order_by(
        HardwareConfiguration.controller_key.asc(),
        HardwareConfiguration.is_active.desc(),
        HardwareConfiguration.updated_at.desc(),
    )
    return list(db.scalars(stmt).all())


def list_hardware_runs(
    db: Session,
    *,
    status_filter: str | None = None,
    site_id: int | None = None,
    limit: int = 50,
) -> list[HardwareRun]:
    """List CODEX hardware execution runs ordered newest first."""
    stmt = select(HardwareRun)
    if status_filter:
        stmt = stmt.where(HardwareRun.status == status_filter)
    if site_id is not None:
        stmt = stmt.where(HardwareRun.site_id == site_id)
    stmt = stmt.order_by(HardwareRun.start_time_utc.desc()).limit(max(1, min(limit, 200)))
    return list(db.scalars(stmt).all())


def list_placeholders_for_version(db: Session, code_version_id: uuid.UUID) -> list[CodePlaceholder]:
    """Return ordered placeholder specifications belonging to a code version."""
    return list(
        db.scalars(
            select(CodePlaceholder)
            .where(CodePlaceholder.code_version_id == code_version_id)
            .order_by(CodePlaceholder.order_index.asc(), CodePlaceholder.placeholder_id.asc())
        ).all()
    )


def create_code_version_with_placeholders(
    db: Session,
    *,
    controller_key: str,
    version_label: str,
    source_code: str,
    language: str,
    board_target: str,
    checksum: str,
    library_manifest: dict[str, Any] | None,
    created_by_admin_id: uuid.UUID | None,
    notes: str | None,
    placeholders: list[dict[str, Any]],
    activate: bool = True,
) -> HardwareCodeVersion:
    """Persist a new immutable firmware source version and its placeholder allow-list."""
    if activate:
        db.execute(
            update(HardwareCodeVersion)
            .where(
                HardwareCodeVersion.controller_key == controller_key,
                HardwareCodeVersion.is_active.is_(True),
            )
            .values(is_active=False)
        )

    cv = HardwareCodeVersion(
        controller_key=controller_key,
        version_label=version_label,
        source_code=source_code,
        language=language,
        board_target=board_target,
        library_manifest=library_manifest,
        checksum=checksum,
        created_by_admin_id=created_by_admin_id,
        is_active=activate,
        notes=notes,
    )
    db.add(cv)
    db.flush()

    for idx, ph in enumerate(placeholders):
        db.add(
            CodePlaceholder(
                code_version_id=cv.code_version_id,
                placeholder_key=ph["placeholder_key"],
                description=ph["description"],
                data_type=ph["data_type"],
                unit=ph.get("unit"),
                required=bool(ph.get("required", True)),
                default_value=ph.get("default_value"),
                validation_schema=ph.get("validation_schema"),
                injection_format=ph.get("injection_format", "cpp_literal"),
                order_index=int(ph.get("order_index", idx)),
            )
        )
    db.flush()
    return cv


def list_firmware_builds(
    db: Session, *, code_version_id: uuid.UUID | None = None
) -> list[FirmwareBuild]:
    """List recorded firmware compilation/build artifacts."""
    stmt = select(FirmwareBuild)
    if code_version_id:
        stmt = stmt.where(FirmwareBuild.code_version_id == code_version_id)
    return list(db.scalars(stmt.order_by(FirmwareBuild.created_at.desc())).all())


def next_command_sequence(db: Session) -> int:
    """Return strictly monotonic command sequence number from codex_command_nonces."""
    current_max = db.scalar(select(func.max(CodexCommandNonce.sequence_number)))
    return int(current_max or 0) + 1


def get_hardware_run(db: Session, hardware_run_id: uuid.UUID) -> HardwareRun | None:
    """Retrieve a CODEX hardware run by UUID."""
    return db.get(HardwareRun, hardware_run_id)


def get_hardware_run_by_idempotency(db: Session, idempotency_key: str) -> HardwareRun | None:
    """Retrieve an existing CODEX hardware run matching an idempotency key."""
    return db.scalar(select(HardwareRun).where(HardwareRun.idempotency_key == idempotency_key))


def list_active_hardware_runs(db: Session) -> list[HardwareRun]:
    """List runs currently prepared or active that E-STOP must abort."""
    return list(
        db.scalars(
            select(HardwareRun).where(
                HardwareRun.status.in_(["prepared", "executing", "dispatched"])
            )
        ).all()
    )


def append_hardware_event(
    db: Session,
    *,
    hardware_run_id: uuid.UUID,
    controller_key: str | None,
    event_type: str,
    message: str,
    severity: str = "info",
    payload: dict[str, Any] | None = None,
) -> HardwareEvent:
    """Append structured event row for hardware run diagnostics."""
    evt = HardwareEvent(
        hardware_run_id=hardware_run_id,
        controller_key=controller_key or "system",
        event_type=event_type,
        message=message,
        severity=severity,
        payload=payload,
    )
    db.add(evt)
    db.flush()
    return evt


def list_hardware_events(db: Session, hardware_run_id: uuid.UUID) -> list[HardwareEvent]:
    """List ordered events for a hardware run."""
    return list(
        db.scalars(
            select(HardwareEvent)
            .where(HardwareEvent.hardware_run_id == hardware_run_id)
            .order_by(HardwareEvent.event_time.asc(), HardwareEvent.event_id.asc())
        ).all()
    )


def record_command_acknowledgement(
    db: Session,
    *,
    hardware_run_id: uuid.UUID,
    command_id: uuid.UUID,
    controller_key: str,
    ack_status: str,
    device_sequence: int | None,
    message: str | None,
    telemetry: dict[str, Any] | None,
) -> HardwareCommandAcknowledgement:
    """Persist controller-specific acknowledgement row."""
    ack = HardwareCommandAcknowledgement(
        hardware_run_id=hardware_run_id,
        command_id=command_id,
        controller_key=controller_key,
        ack_status=ack_status,
        device_sequence=device_sequence,
        message=message,
        telemetry=telemetry,
    )
    db.add(ack)
    db.flush()
    return ack


def list_command_acknowledgements(
    db: Session, hardware_run_id: uuid.UUID
) -> list[HardwareCommandAcknowledgement]:
    """List acknowledgements associated with a hardware run."""
    return list(
        db.scalars(
            select(HardwareCommandAcknowledgement)
            .where(HardwareCommandAcknowledgement.hardware_run_id == hardware_run_id)
            .order_by(HardwareCommandAcknowledgement.ack_id.asc())
        ).all()
    )


def get_published_site(db: Session, site_id: int) -> LandingSite | None:
    """Fetch landing site record regardless of status (caller checks published)."""
    return db.get(LandingSite, site_id)


def get_simulation_run(db: Session, simulation_id: uuid.UUID) -> SimulationRun | None:
    """Fetch scientific simulation run record."""
    return db.get(SimulationRun, simulation_id)


def get_simulation_terminal_sample(
    db: Session, simulation_id: uuid.UUID
) -> SimulationSample | None:
    """Return final (or latest) time-series sample for orbital angle extraction."""
    return db.scalar(
        select(SimulationSample)
        .where(SimulationSample.simulation_id == simulation_id)
        .order_by(SimulationSample.sample_index.desc())
        .limit(1)
    )


def utc_now() -> datetime:
    """Return timezone-aware UTC timestamp."""
    return datetime.now(UTC)
