"""Admin overview, audit log explorer, live system health probes, and provenance management."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.audit import log_audit, redact_audit_value
from app.core.auth_dependency import RequireRole, get_admin_roles, get_current_admin
from app.core.config import settings
from app.db.session import get_db
from app.integrations.spice.ephemeris import summarize_kernel_metadata
from app.integrations.spice.kernel_manager import SpiceKernelError, spice_kernel_manager
from app.integrations.terrain.dem_reader import DEMRegistry
from app.models.admin import Admin, AuditLog, HealthCheck, SystemComponent
from app.models.catalogue import LandingSite, SiteMedia
from app.models.codex import HardwareCodeVersion, HardwareDevice
from app.models.metrics import ParameterDefinition
from app.models.operations import BackgroundJob
from app.models.provenance import DatasetImport, DataSource
from app.models.simulation import SimulationRun
from app.schemas.admin_portal import (
    AdminOverviewOut,
    AuditLogEntryOut,
    AuditLogPageOut,
    DataSourceCreateIn,
    DataSourceOut,
    DataSourceUpdateIn,
    ParameterDefinitionAdminOut,
    SystemComponentHealthOut,
    SystemHealthSummaryOut,
)

router = APIRouter(prefix="/admin", tags=["Admin Overview, Audit & Health"])


def _ensure_system_component(
    db: Session,
    *,
    component_key: str,
    display_name: str,
    component_type: str,
) -> SystemComponent:
    comp = db.scalar(select(SystemComponent).where(SystemComponent.component_key == component_key))
    if comp is None:
        comp = SystemComponent(
            component_key=component_key,
            display_name=display_name,
            component_type=component_type,
            is_enabled=True,
        )
        db.add(comp)
        db.flush()
    return comp


def _record_probe(
    db: Session,
    *,
    component_key: str,
    display_name: str,
    component_type: str,
    status_val: Literal["healthy", "degraded", "unavailable"],
    latency_ms: int | None,
    details: dict,
    error_message: str | None = None,
) -> SystemComponentHealthOut:
    comp = _ensure_system_component(
        db,
        component_key=component_key,
        display_name=display_name,
        component_type=component_type,
    )
    now = datetime.now(UTC)
    row = HealthCheck(
        component_id=comp.component_id,
        status=status_val,
        latency_ms=latency_ms,
        details=details,
        error_message=error_message,
        checked_at=now,
    )
    db.add(row)
    db.flush()
    return SystemComponentHealthOut(
        component_key=component_key,
        display_name=display_name,
        component_type=component_type,
        status=status_val,
        latency_ms=latency_ms,
        details=details,
        error_message=error_message,
        checked_at=now,
    )


@router.get(
    "/overview",
    response_model=AdminOverviewOut,
    summary="Role-filtered administrative overview summary",
)
def get_admin_overview(
    admin: Annotated[Admin, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> AdminOverviewOut:
    """Return operational counts filtered strictly according to caller's RBAC roles."""
    roles = sorted(get_admin_roles(db, str(admin.admin_id)))
    role_set = set(roles)

    status_counts = {
        row[0]: int(row[1])
        for row in db.execute(
            select(LandingSite.catalogue_status, func.count(LandingSite.site_id)).group_by(
                LandingSite.catalogue_status
            )
        ).all()
    }
    sites_total = sum(status_counts.values())
    media_total = int(db.scalar(select(func.count()).select_from(SiteMedia)) or 0)
    imports_total = int(db.scalar(select(func.count()).select_from(DatasetImport)) or 0)
    imports_open = int(
        db.scalar(
            select(func.count())
            .select_from(DatasetImport)
            .where(DatasetImport.status.in_(["staged", "validating", "previewed"]))
        )
        or 0
    )
    simulations_total = int(db.scalar(select(func.count()).select_from(SimulationRun)) or 0)

    codex_online: int | None = None
    codex_total: int | None = None
    codex_mode: str | None = None
    active_fw_count: int | None = None
    if "super_admin" in role_set or role_set & {
        "hardware_admin",
        "hardware_operator",
        "system_admin",
    }:
        devices = list(db.scalars(select(HardwareDevice)).all())
        codex_total = len(devices)
        codex_online = sum(
            1
            for d in devices
            if d.health_state in {"ready", "busy", "completed", "online_unverified"}
        )
        codex_mode = settings.CODEX_TRANSPORT_MODE
        active_fw_count = int(
            db.scalar(
                select(func.count())
                .select_from(HardwareCodeVersion)
                .where(HardwareCodeVersion.is_active.is_(True))
            )
            or 0
        )

    audit_24h: int | None = None
    degraded_count: int | None = None
    if "super_admin" in role_set or "system_admin" in role_set:
        since = datetime.now(UTC) - timedelta(hours=24)
        audit_24h = int(
            db.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.occurred_at >= since)
            )
            or 0
        )
        # Count distinct components whose most recent health_check is degraded/unavailable
        latest_sub = (
            select(
                HealthCheck.component_id,
                func.max(HealthCheck.health_check_id).label("max_id"),
            )
            .group_by(HealthCheck.component_id)
            .subquery()
        )
        degraded_count = int(
            db.scalar(
                select(func.count())
                .select_from(HealthCheck)
                .join(latest_sub, HealthCheck.health_check_id == latest_sub.c.max_id)
                .where(HealthCheck.status != "healthy")
            )
            or 0
        )

    return AdminOverviewOut(
        username=admin.username,
        display_name=admin.display_name,
        roles=roles,
        sites_total=sites_total,
        sites_published=status_counts.get("published", 0),
        sites_draft=status_counts.get("draft", 0),
        sites_verified=status_counts.get("verified", 0),
        sites_archived=status_counts.get("archived", 0),
        media_total=media_total,
        imports_total=imports_total,
        imports_open=imports_open,
        simulations_total=simulations_total,
        codex_controllers_online=codex_online,
        codex_controllers_total=codex_total,
        codex_transport_mode=codex_mode,
        active_firmware_versions_count=active_fw_count,
        recent_audit_count_24h=audit_24h,
        degraded_components_count=degraded_count,
    )


@router.get(
    "/audit-logs",
    response_model=AuditLogPageOut,
    summary="Explore redacted administrative audit log entries",
)
def list_audit_logs(
    _admin: Annotated[Admin, Depends(RequireRole("system_admin"))],
    db: Annotated[Session, Depends(get_db)],
    action_key: Annotated[str | None, Query()] = None,
    entity_type: Annotated[str | None, Query()] = None,
    admin_id: Annotated[UUID | None, Query()] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AuditLogPageOut:
    """List filterable, paginated audit trail records with sensitive snapshots redacted."""
    stmt = select(AuditLog, Admin.username).outerjoin(Admin, AuditLog.admin_id == Admin.admin_id)
    if action_key:
        stmt = stmt.where(AuditLog.action_key.ilike(f"%{action_key.strip()}%"))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type.strip())
    if admin_id:
        stmt = stmt.where(AuditLog.admin_id == admin_id)
    if date_from:
        stmt = stmt.where(AuditLog.occurred_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.occurred_at <= date_to)

    total = int(db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0)
    rows = list(
        db.execute(
            stmt.order_by(AuditLog.occurred_at.desc(), AuditLog.audit_id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )

    items = [
        AuditLogEntryOut(
            audit_id=entry.audit_id,
            admin_id=entry.admin_id,
            admin_username=username,
            action_key=entry.action_key,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            before_snapshot=redact_audit_value(entry.before_snapshot)
            if entry.before_snapshot is not None
            else None,
            after_snapshot=redact_audit_value(entry.after_snapshot)
            if entry.after_snapshot is not None
            else None,
            ip_address=str(entry.ip_address) if entry.ip_address else None,
            occurred_at=entry.occurred_at,
        )
        for entry, username in rows
    ]

    return AuditLogPageOut(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


@router.get(
    "/system/health",
    response_model=SystemHealthSummaryOut,
    summary="Execute live subsystem health probes and record telemetry (omits host OS paths)",
)
def get_admin_system_health(
    _admin: Annotated[Admin, Depends(RequireRole("system_admin"))],
    db: Annotated[Session, Depends(get_db)],
) -> SystemHealthSummaryOut:
    """Run live checks for DB, SPICE, LOLA DEM, Ollama, Worker queue, and CODEX transport."""
    results: list[SystemComponentHealthOut] = []

    # 1. PostgreSQL
    t0 = time.perf_counter()
    try:
        db.execute(text("SELECT 1;"))
        db_ms = int((time.perf_counter() - t0) * 1000)
        results.append(
            _record_probe(
                db,
                component_key="postgresql",
                display_name="PostgreSQL 18 Database",
                component_type="database",
                status_val="healthy",
                latency_ms=db_ms,
                details={"engine": "PostgreSQL 18 + psycopg 3"},
            )
        )
    except (SQLAlchemyError, OSError) as exc:
        results.append(
            _record_probe(
                db,
                component_key="postgresql",
                display_name="PostgreSQL 18 Database",
                component_type="database",
                status_val="unavailable",
                latency_ms=None,
                details={},
                error_message=str(exc),
            )
        )

    # 2. NAIF SPICE Kernels
    t0 = time.perf_counter()
    try:
        kstate = spice_kernel_manager.ensure_loaded()
        spice_ms = int((time.perf_counter() - t0) * 1000)
        manifest = summarize_kernel_metadata(kstate)
        kernels_raw = manifest.get("kernels")
        kernels_count = len(kernels_raw) if isinstance(kernels_raw, list) else 0
        results.append(
            _record_probe(
                db,
                component_key="spice_ephemeris",
                display_name="NAIF SPICE Ephemeris Engine",
                component_type="science_engine",
                status_val="healthy",
                latency_ms=spice_ms,
                details={
                    "loaded_kernels_count": kernels_count,
                    "available_frames": list(kstate.available_frames.keys()),
                },
            )
        )
    except (SpiceKernelError, OSError, ValueError, RuntimeError) as exc:
        results.append(
            _record_probe(
                db,
                component_key="spice_ephemeris",
                display_name="NAIF SPICE Ephemeris Engine",
                component_type="science_engine",
                status_val="degraded",
                latency_ms=None,
                details={},
                error_message=str(exc),
            )
        )

    # 3. LOLA DEM Rasters
    t0 = time.perf_counter()
    try:
        assets = DEMRegistry().list_assets()
        dem_ms = int((time.perf_counter() - t0) * 1000)
        results.append(
            _record_probe(
                db,
                component_key="lola_dem_rasters",
                display_name="LOLA DEM Terrain Rasters",
                component_type="science_engine",
                status_val="healthy" if assets else "degraded",
                latency_ms=dem_ms,
                details={
                    "asset_count": len(assets),
                    "asset_ids": [a.asset_id for a in assets],
                },
            )
        )
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        results.append(
            _record_probe(
                db,
                component_key="lola_dem_rasters",
                display_name="LOLA DEM Terrain Rasters",
                component_type="science_engine",
                status_val="degraded",
                latency_ms=None,
                details={},
                error_message=str(exc),
            )
        )

    # 4. Local Ollama AI Assist
    t0 = time.perf_counter()
    try:
        resp = httpx.get(f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=0.6)
        ollama_ms = int((time.perf_counter() - t0) * 1000)
        if resp.status_code == 200:
            models_payload = resp.json().get("models", [])
            model_names = [m.get("name") for m in models_payload if isinstance(m, dict)]
            results.append(
                _record_probe(
                    db,
                    component_key="ollama_llm",
                    display_name="Local Ollama AI Assist",
                    component_type="llm_service",
                    status_val="healthy",
                    latency_ms=ollama_ms,
                    details={
                        "configured_model": settings.OLLAMA_MODEL,
                        "available_models_count": len(model_names),
                    },
                )
            )
        else:
            results.append(
                _record_probe(
                    db,
                    component_key="ollama_llm",
                    display_name="Local Ollama AI Assist",
                    component_type="llm_service",
                    status_val="degraded",
                    latency_ms=ollama_ms,
                    details={
                        "configured_model": settings.OLLAMA_MODEL,
                        "fallback": "deterministic",
                    },
                    error_message=f"Ollama daemon returned HTTP {resp.status_code}; fallback active.",
                )
            )
    except (httpx.HTTPError, OSError):
        results.append(
            _record_probe(
                db,
                component_key="ollama_llm",
                display_name="Local Ollama AI Assist",
                component_type="llm_service",
                status_val="degraded",
                latency_ms=None,
                details={"configured_model": settings.OLLAMA_MODEL, "fallback": "deterministic"},
                error_message="Local Ollama daemon unreachable; deterministic rule-based fallback active.",
            )
        )

    # 5. Background Simulation Worker Queue
    now = datetime.now(UTC)
    queued_jobs = int(
        db.scalar(
            select(func.count()).select_from(BackgroundJob).where(BackgroundJob.status == "QUEUED")
        )
        or 0
    )
    stale_running = int(
        db.scalar(
            select(func.count())
            .select_from(BackgroundJob)
            .where(
                BackgroundJob.status == "RUNNING",
                BackgroundJob.lease_expires_at.is_not(None),
                BackgroundJob.lease_expires_at < now,
            )
        )
        or 0
    )
    results.append(
        _record_probe(
            db,
            component_key="simulation_worker",
            display_name="Background Simulation Worker",
            component_type="worker",
            status_val="degraded" if stale_running > 0 else "healthy",
            latency_ms=1,
            details={"queued_jobs": queued_jobs, "stale_leases": stale_running},
            error_message=f"{stale_running} stale job lease(s) detected."
            if stale_running > 0
            else None,
        )
    )

    # 6. CODEX Hardware Transport
    devices = list(db.scalars(select(HardwareDevice)).all())
    unverified_cnt = sum(1 for d in devices if d.verification_status != "bench_verified")
    estop_active = any(d.estop_latched for d in devices)
    results.append(
        _record_probe(
            db,
            component_key="codex_hardware",
            display_name="CODEX Hardware Transport & Bench",
            component_type="hardware",
            status_val="degraded" if unverified_cnt > 0 or estop_active else "healthy",
            latency_ms=1,
            details={
                "transport_mode": settings.CODEX_TRANSPORT_MODE,
                "require_verified_bench": settings.CODEX_REQUIRE_VERIFIED_BENCH,
                "controllers_registered": len(devices),
                "unverified_controllers": unverified_cnt,
                "estop_latched": estop_active,
            },
            error_message=(
                "Physical bench calibration and hardware verification pending."
                if unverified_cnt > 0
                else None
            ),
        )
    )

    db.commit()

    statuses = {c.status for c in results}
    overall: Literal["healthy", "degraded", "unavailable"] = "healthy"
    if "unavailable" in statuses:
        overall = "unavailable"
    elif "degraded" in statuses:
        overall = "degraded"

    return SystemHealthSummaryOut(
        overall_status=overall,
        checked_at=datetime.now(UTC),
        components=results,
    )


@router.get(
    "/parameters",
    response_model=list[ParameterDefinitionAdminOut],
    summary="List registered scientific parameter definitions for metric curation",
)
def list_admin_parameters(
    _admin: Annotated[
        Admin, Depends(RequireRole("site_editor", "research_admin", "system_admin", "viewer"))
    ],
    db: Annotated[Session, Depends(get_db)],
) -> list[ParameterDefinitionAdminOut]:
    params = list(
        db.scalars(
            select(ParameterDefinition).order_by(ParameterDefinition.parameter_key.asc())
        ).all()
    )
    return [
        ParameterDefinitionAdminOut(
            parameter_id=p.parameter_id,
            parameter_key=p.parameter_key,
            display_name=p.display_name,
            description=p.description,
            unit=p.unit,
            value_type=p.value_type,
            comparison_direction=p.comparison_direction,
            target_value=p.target_value,
            is_comparable=p.is_comparable,
            is_time_dependent=p.is_time_dependent,
            validation_min=p.validation_min,
            validation_max=p.validation_max,
            is_active=p.is_active,
        )
        for p in params
    ]


@router.get(
    "/sources",
    response_model=list[DataSourceOut],
    summary="List scientific provenance data sources",
)
def list_data_sources(
    _admin: Annotated[
        Admin, Depends(RequireRole("site_editor", "research_admin", "system_admin", "viewer"))
    ],
    db: Annotated[Session, Depends(get_db)],
) -> list[DataSourceOut]:
    rows = list(db.scalars(select(DataSource).order_by(DataSource.source_id.desc())).all())
    return [
        DataSourceOut(
            source_id=s.source_id,
            agency_name=s.agency_name,
            title=s.title,
            publisher=s.publisher,
            source_url=s.source_url,
            publication_date=s.publication_date,
            accessed_at=s.accessed_at,
            dataset_version=s.dataset_version,
            licence=s.licence,
            citation_text=s.citation_text,
            checksum=s.checksum,
        )
        for s in rows
    ]


@router.post(
    "/sources",
    response_model=DataSourceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a provenance data source citation record",
)
def create_data_source(
    payload: DataSourceCreateIn,
    admin: Annotated[Admin, Depends(RequireRole("research_admin", "site_editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> DataSourceOut:
    src = DataSource(**payload.model_dump(), accessed_at=datetime.now(UTC))
    db.add(src)
    db.flush()
    log_audit(
        db,
        action_key="SOURCE_CREATE",
        entity_type="data_sources",
        entity_id=str(src.source_id),
        admin_id=str(admin.admin_id),
        after_snapshot={"title": src.title, "agency_name": src.agency_name},
    )
    db.commit()
    db.refresh(src)
    return DataSourceOut(
        source_id=src.source_id,
        agency_name=src.agency_name,
        title=src.title,
        publisher=src.publisher,
        source_url=src.source_url,
        publication_date=src.publication_date,
        accessed_at=src.accessed_at,
        dataset_version=src.dataset_version,
        licence=src.licence,
        citation_text=src.citation_text,
        checksum=src.checksum,
    )


@router.patch(
    "/sources/{source_id}",
    response_model=DataSourceOut,
    summary="Update an existing scientific provenance data source",
)
def update_data_source(
    source_id: int,
    payload: DataSourceUpdateIn,
    admin: Annotated[Admin, Depends(RequireRole("research_admin", "site_editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> DataSourceOut:
    src = db.get(DataSource, source_id)
    if not src:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Data source ID {source_id} was not found.",
        )
    update_dict = payload.model_dump(exclude_unset=True)
    before = {"title": src.title, "dataset_version": src.dataset_version}
    for k, v in update_dict.items():
        if hasattr(src, k):
            setattr(src, k, v)
    db.flush()
    log_audit(
        db,
        action_key="SOURCE_UPDATE",
        entity_type="data_sources",
        entity_id=str(src.source_id),
        admin_id=str(admin.admin_id),
        before_snapshot=before,
        after_snapshot=update_dict,
    )
    db.commit()
    db.refresh(src)
    return DataSourceOut(
        source_id=src.source_id,
        agency_name=src.agency_name,
        title=src.title,
        publisher=src.publisher,
        source_url=src.source_url,
        publication_date=src.publication_date,
        accessed_at=src.accessed_at,
        dataset_version=src.dataset_version,
        licence=src.licence,
        citation_text=src.citation_text,
        checksum=src.checksum,
    )
