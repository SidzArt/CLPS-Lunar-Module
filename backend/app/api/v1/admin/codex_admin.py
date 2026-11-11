"""Administrative REST routes for CODEX diagnostics, calibrations, LED mapping, and code."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.audit import log_audit
from app.core.auth_dependency import RequireRole
from app.db.session import get_db
from app.models.admin import Admin
from app.repositories import codex_repo
from app.schemas.codex import (
    AdminDevicesListOut,
    CalibrationCreateIn,
    CalibrationProfileOut,
    CalibrationUpdateIn,
    CodeVersionCreateIn,
    CodeVersionDetailOut,
    CodeVersionDiffOut,
    CodeVersionOut,
    CodeVersionRenderIn,
    CodeVersionSyntaxValidationOut,
    DeviceHeartbeatIn,
    HardwareConfigurationOut,
    HardwareRunAdminSummaryOut,
    HardwareVariableRefOut,
    MoonLedRegionOut,
    MoonLedRegionUpsertIn,
)
from app.services import codex_service

router = APIRouter(prefix="/admin", tags=["CODEX Hardware Admin"])

HardwareAdminUser = Annotated[
    Admin,
    Depends(RequireRole("hardware_admin", "system_admin")),
]


class ConfigurationUpsertIn(BaseModel):
    """Register or update active controller hardware configuration baseline."""

    board_model: str = Field(..., min_length=2, max_length=100)
    firmware_target: str = Field(..., min_length=2, max_length=100)
    motor_type: str | None = None
    steps_per_revolution: int | None = None
    microstep_setting: int | None = None
    gear_ratio: float | None = None
    driver_model: str | None = None
    current_limit_setting: float | None = None
    led_count: int | None = None
    led_mapping_version: str | None = None
    config_json: dict[str, Any] | None = None


@router.get(
    "/codex/devices",
    response_model=AdminDevicesListOut,
    status_code=status.HTTP_200_OK,
    summary="Inspect detailed three-controller diagnostics and active hardware configurations",
)
def admin_list_codex_devices(
    admin: HardwareAdminUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Return hosts, firmware versions/checksums, link flags, E-STOP latches, and configs."""
    return codex_service.get_admin_devices_payload(db)


@router.post(
    "/codex/devices/{controller_key}/heartbeat",
    response_model=AdminDevicesListOut,
    status_code=status.HTTP_200_OK,
    summary="Probe controller via active transport or ingest verified heartbeat telemetry",
)
def admin_device_heartbeat(
    controller_key: str,
    payload: DeviceHeartbeatIn,
    admin: HardwareAdminUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Refresh three-controller heartbeat, firmware identity, and health FSM."""
    return codex_service.update_device_heartbeat(
        db,
        controller_key=controller_key,
        payload=payload.model_dump(),
        admin_id=admin.admin_id,
    )


@router.put(
    "/codex/configurations/{controller_key}",
    status_code=status.HTTP_200_OK,
    summary="Create or rotate active hardware configuration baseline for a controller",
)
def admin_upsert_hardware_configuration(
    controller_key: str,
    payload: ConfigurationUpsertIn,
    admin: HardwareAdminUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Rotate active controller hardware configuration with audit trail."""
    if controller_key not in codex_service.ALL_CONTROLLER_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported controller_key '{controller_key}'.",
        )
    cfg = codex_repo.upsert_hardware_configuration(
        db,
        controller_key=controller_key,
        **payload.model_dump(),
    )
    log_audit(
        db,
        action_key="CODEX_CONFIGURATION_UPSERT",
        entity_type="hardware_configuration",
        entity_id=str(cfg.hardware_config_id),
        admin_id=str(admin.admin_id),
        after_snapshot={"controller_key": controller_key, "board_model": cfg.board_model},
    )
    db.commit()
    return {
        "hardware_config_id": str(cfg.hardware_config_id),
        "controller_key": cfg.controller_key,
        "board_model": cfg.board_model,
        "firmware_target": cfg.firmware_target,
        "is_active": cfg.is_active,
    }


@router.get(
    "/codex/configurations",
    response_model=list[HardwareConfigurationOut],
    status_code=status.HTTP_200_OK,
    summary="List stored hardware configuration baselines across CODEX controllers",
)
def admin_list_hardware_configurations(
    admin: HardwareAdminUser,
    db: Annotated[Session, Depends(get_db)],
    controller_key: Annotated[str | None, Query()] = None,
) -> list[dict[str, Any]]:
    """Inspect active and historical controller configuration baselines."""
    return codex_service.list_hardware_configurations_admin(db, controller_key=controller_key)


@router.get(
    "/codex/runs",
    response_model=list[HardwareRunAdminSummaryOut],
    status_code=status.HTTP_200_OK,
    summary="List CODEX hardware execution and dry-run preparation history",
)
def admin_list_hardware_runs(
    admin: HardwareAdminUser,
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    site_id: Annotated[int | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[dict[str, Any]]:
    """Return ordered hardware runs for administrative inspection and telemetry auditing."""
    return codex_service.list_hardware_runs_admin(
        db,
        status_filter=status_filter,
        site_id=site_id,
        limit=limit,
    )


@router.get(
    "/codex/calibrations",
    response_model=list[CalibrationProfileOut],
    status_code=status.HTTP_200_OK,
    summary="List versioned motor calibration profiles",
)
def admin_list_calibrations(
    admin: HardwareAdminUser,
    db: Annotated[Session, Depends(get_db)],
    motor_key: Annotated[str | None, Query()] = None,
    active_only: Annotated[bool, Query()] = False,
) -> list[Any]:
    """List NEMA17 and BYJ calibration versions without hiding superseded rows."""
    return codex_repo.list_motor_calibrations(db, motor_key=motor_key, active_only=active_only)


@router.post(
    "/codex/calibrations",
    response_model=CalibrationProfileOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new versioned motor calibration profile",
)
def admin_create_calibration(
    payload: CalibrationCreateIn,
    admin: HardwareAdminUser,
    db: Annotated[Session, Depends(get_db)],
) -> Any:
    """Insert a new motor calibration version cleanly without overwriting prior records."""
    return codex_service.create_calibration_profile(
        db,
        payload=payload.model_dump(),
        admin_id=admin.admin_id,
    )


@router.patch(
    "/codex/calibrations",
    response_model=CalibrationProfileOut,
    status_code=status.HTTP_200_OK,
    summary="Update verification status or notes on an existing calibration version",
)
def admin_update_calibration(
    payload: CalibrationUpdateIn,
    admin: HardwareAdminUser,
    db: Annotated[Session, Depends(get_db)],
) -> Any:
    """Promote calibration profile to bench_verified or mark deprecated."""
    return codex_service.update_calibration_status(
        db,
        calibration_id=payload.calibration_id,
        verification_status=payload.verification_status,
        calibration_notes=payload.calibration_notes,
        measured_by=payload.measured_by,
        is_active=payload.is_active,
        admin_id=admin.admin_id,
    )


@router.get(
    "/codex/led-mapping",
    response_model=list[MoonLedRegionOut],
    status_code=status.HTTP_200_OK,
    summary="List all 13 Moon LED region polygons, centroids, and physical pixel mappings",
)
def admin_list_led_mapping(
    admin: HardwareAdminUser,
    db: Annotated[Session, Depends(get_db)],
) -> list[dict[str, Any]]:
    """Inspect current 13-region Moon LED mapping table and verification states."""
    return codex_service.list_moon_led_regions_payload(db)


@router.post(
    "/codex/led-mapping",
    response_model=MoonLedRegionOut,
    status_code=status.HTTP_200_OK,
    summary="Create or update one of the 13 Moon LED physical region mappings",
)
def admin_upsert_led_mapping(
    payload: MoonLedRegionUpsertIn,
    admin: HardwareAdminUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Persist verified or unverified polygon, centroid, and pixel indices for regions 1..13."""
    region, pixels = codex_service.upsert_moon_led_region(
        db,
        payload=payload.model_dump(),
        admin_id=admin.admin_id,
    )
    return {
        "region_id": region.region_id,
        "region_index": region.region_index,
        "region_name": region.region_name,
        "centroid_lat": float(region.centroid_lat) if region.centroid_lat is not None else None,
        "centroid_lon": float(region.centroid_lon) if region.centroid_lon is not None else None,
        "boundary_polygon": region.boundary_polygon,
        "pixel_indices": list(region.pixel_indices or []),
        "mapping_version": region.mapping_version,
        "orientation_reference": region.orientation_reference,
        "verification_status": region.verification_status,
        "geometry_source": region.geometry_source,
        "is_active": bool(region.is_active),
        "normalized_pixels": pixels,
    }


@router.get(
    "/hardware/code-versions",
    response_model=list[CodeVersionOut],
    status_code=status.HTTP_200_OK,
    summary="List immutable controller firmware code versions and placeholder manifests",
)
def admin_list_code_versions(
    admin: HardwareAdminUser,
    db: Annotated[Session, Depends(get_db)],
    controller_key: Annotated[str | None, Query()] = None,
) -> list[dict[str, Any]]:
    """Return firmware code versions tracked in PostgreSQL with allow-listed placeholders."""
    versions = codex_repo.list_code_versions(db, controller_key=controller_key)
    return [codex_service.serialize_code_version(db, cv) for cv in versions]


@router.post(
    "/hardware/code-versions",
    response_model=CodeVersionDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register an immutable firmware code version with allow-listed placeholders",
)
def admin_create_code_version(
    payload: CodeVersionCreateIn,
    admin: HardwareAdminUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Store SHA-256 verified firmware template and declared placeholder allow-list."""
    return codex_service.create_code_version(
        db,
        payload=payload.model_dump(),
        admin_id=admin.admin_id,
    )


@router.get(
    "/hardware/code-versions/{code_version_id}",
    response_model=CodeVersionDetailOut,
    status_code=status.HTTP_200_OK,
    summary="Inspect full immutable firmware source code, checksum, placeholders, and builds",
)
def admin_get_code_version_detail(
    code_version_id: UUID,
    admin: HardwareAdminUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Fetch full immutable source code and provenance for the split-pane Firmware Editor."""
    return codex_service.get_code_version_detail(db, code_version_id)


@router.post(
    "/hardware/code-versions/{code_version_id}/activate",
    response_model=CodeVersionDetailOut,
    status_code=status.HTTP_200_OK,
    summary="Promote an immutable firmware version as active for its controller without flashing",
)
def admin_activate_code_version(
    code_version_id: UUID,
    admin: HardwareAdminUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Mark an existing immutable version active in PostgreSQL without physical flashing."""
    return codex_service.activate_code_version(
        db,
        code_version_id=code_version_id,
        admin_id=admin.admin_id,
    )


@router.get(
    "/hardware/code-versions/{code_version_id}/diff/{other_version_id}",
    response_model=CodeVersionDiffOut,
    status_code=status.HTTP_200_OK,
    summary="Compute unified line and placeholder diff between two firmware versions",
)
def admin_diff_code_versions(
    code_version_id: UUID,
    other_version_id: UUID,
    admin: HardwareAdminUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Compare two immutable versions belonging to the same controller."""
    return codex_service.compare_code_versions(
        db,
        base_version_id=code_version_id,
        target_version_id=other_version_id,
    )


@router.post(
    "/hardware/code-versions/{code_version_id}/validate-syntax",
    response_model=CodeVersionSyntaxValidationOut,
    status_code=status.HTTP_200_OK,
    summary="Run static C/C++ delimiter, safety-guard, and placeholder validation",
)
def admin_validate_code_version_syntax(
    code_version_id: UUID,
    admin: HardwareAdminUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Validate firmware placeholders and structure statically without compilation or flashing."""
    return codex_service.validate_code_version_syntax(db, code_version_id=code_version_id)


@router.post(
    "/hardware/code-versions/{code_version_id}/render-preview",
    status_code=status.HTTP_200_OK,
    summary="Render allow-listed {{PLACEHOLDER}} values into firmware template without uploading",
)
def admin_render_code_version_preview(
    code_version_id: UUID,
    payload: CodeVersionRenderIn,
    admin: HardwareAdminUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Safely render strict placeholders for inspection and checksum verification."""
    return codex_service.render_code_version_preview(
        db,
        code_version_id=code_version_id,
        values=payload.values,
    )


@router.get(
    "/hardware/variables",
    response_model=list[HardwareVariableRefOut],
    status_code=status.HTTP_200_OK,
    summary="List live backend-driven hardware/kinematics/LED variables for Firmware Editor",
)
def admin_list_hardware_variables(
    admin: HardwareAdminUser,
    db: Annotated[Session, Depends(get_db)],
) -> list[dict[str, Any]]:
    """Return authoritative live database variables and active placeholder definitions."""
    return codex_service.list_hardware_variables_catalog(db)
