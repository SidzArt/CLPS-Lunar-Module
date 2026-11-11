"""Repository layer for scientific simulations, horizon profile cache, and job queueing."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.catalogue import LandingSite
from app.models.operations import BackgroundJob
from app.models.simulation import (
    SimulationEventWindow,
    SimulationMetric,
    SimulationRun,
    SimulationSample,
    TerrainHorizonProfile,
)
from app.services.horizon import HorizonComputationResult

JOB_TYPE_SIMULATION = "SIMULATION_RUN"


def get_site_for_simulation(db: Session, site_id: int) -> LandingSite | None:
    """Fetch landing site by primary ID."""
    return db.get(LandingSite, site_id)


def get_simulation_run(db: Session, simulation_id: uuid.UUID) -> SimulationRun | None:
    """Fetch simulation run by UUID."""
    return db.get(SimulationRun, simulation_id)


def get_job_for_run(db: Session, job_id: uuid.UUID | None) -> BackgroundJob | None:
    """Fetch linked background job if present."""
    if job_id is None:
        return None
    return db.get(BackgroundJob, job_id)


def get_run_by_idempotency_key(
    db: Session, idempotency_key: str
) -> tuple[SimulationRun, BackgroundJob] | None:
    """Find an existing non-failed simulation run matching an idempotency token."""
    job = db.scalar(select(BackgroundJob).where(BackgroundJob.idempotency_key == idempotency_key))
    if job is None:
        return None
    sim_id_raw = job.payload.get("simulation_id") if isinstance(job.payload, dict) else None
    if not sim_id_raw:
        return None
    run = db.get(SimulationRun, uuid.UUID(str(sim_id_raw)))
    if run is None:
        return None
    return run, job


def create_simulation_with_job(
    db: Session,
    *,
    site_id: int,
    start_time_utc: datetime,
    end_time_utc: datetime,
    duration_seconds: int,
    playback_speed: float,
    sample_interval_seconds: int,
    ephemeris_source: str,
    ephemeris_version: str,
    coordinate_frame: str,
    aberration_policy: str,
    terrain_dataset_id: str | None,
    algorithm_version: str,
    sampling_policy: dict[str, Any],
    kernel_manifest: dict[str, Any],
    quality_state: str,
    quality_warnings: list[str],
    request_id: str | None,
    idempotency_key: str | None,
) -> tuple[SimulationRun, BackgroundJob]:
    """Create both SimulationRun and queued BackgroundJob in a single atomic transaction."""
    sim_id = uuid.uuid4()
    job = BackgroundJob(
        job_type=JOB_TYPE_SIMULATION,
        payload={"simulation_id": str(sim_id), "site_id": site_id},
        priority=50,
        status="QUEUED",
        attempts=0,
        max_attempts=3,
        progress_pct=0.0,
        progress_message="Queued for simulation worker execution",
        idempotency_key=idempotency_key,
    )
    db.add(job)
    db.flush()

    run = SimulationRun(
        simulation_id=sim_id,
        site_id=site_id,
        job_id=job.job_id,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
        duration_seconds=duration_seconds,
        playback_speed=playback_speed,
        sample_interval_seconds=sample_interval_seconds,
        ephemeris_source=ephemeris_source,
        ephemeris_version=ephemeris_version,
        coordinate_frame=coordinate_frame,
        aberration_policy=aberration_policy,
        terrain_dataset_id=terrain_dataset_id,
        algorithm_version=algorithm_version,
        sampling_policy=sampling_policy,
        kernel_manifest=kernel_manifest,
        quality_state=quality_state,
        quality_warnings=quality_warnings,
        status="queued",
        progress_pct=0.0,
        request_id=request_id,
    )
    db.add(run)
    db.commit()
    db.refresh(job)
    db.refresh(run)
    return run, job


def get_cached_horizon_profile(db: Session, cache_key: str) -> TerrainHorizonProfile | None:
    """Look up persisted horizon profile by deterministic cache key."""
    return db.scalar(
        select(TerrainHorizonProfile).where(TerrainHorizonProfile.cache_key == cache_key)
    )


def save_horizon_profile_idempotent(
    db: Session, result: HorizonComputationResult
) -> TerrainHorizonProfile:
    """Persist computed DEM horizon profile safely with PostgreSQL ON CONFLICT DO NOTHING."""
    if (
        result.dem_asset_id is None
        or result.dem_checksum is None
        or result.dem_resolution_m is None
    ):
        raise ValueError("Cannot cache geometric-only fallback without DEM metadata")

    stmt = (
        pg_insert(TerrainHorizonProfile)
        .values(
            site_id=result.site_id,
            cache_key=result.cache_key,
            site_latitude_deg=result.site_latitude_deg,
            site_longitude_deg=result.site_longitude_deg,
            site_elevation_m=result.site_ground_elevation_m,
            observer_height_m=result.observer_height_m,
            coordinate_frame=result.coordinate_frame,
            dem_asset_id=result.dem_asset_id,
            dem_checksum=result.dem_checksum,
            dem_resolution_m=result.dem_resolution_m,
            algorithm_version=result.algorithm_version,
            azimuth_bins=result.azimuth_bins,
            azimuths_deg=result.azimuths_deg,
            horizon_elevations_deg=result.horizon_elevations_deg,
            horizon_distances_m=result.horizon_distances_m,
            uncertainty_deg=result.uncertainty_deg,
            quality_state=result.profile.quality_state,
            coverage_fraction=result.coverage_fraction,
            metadata_json=result.metadata,
        )
        .on_conflict_do_nothing(index_elements=["cache_key"])
    )
    db.execute(stmt)
    db.commit()
    cached = get_cached_horizon_profile(db, result.cache_key)
    if cached is None:
        raise RuntimeError("Failed to retrieve cached horizon profile after upsert")
    return cached


def claim_next_simulation_job(
    db: Session,
    worker_id: str,
    lease_seconds: int = 300,
) -> BackgroundJob | None:
    """Claim next queued or expired-lease simulation job using FOR UPDATE SKIP LOCKED."""
    now = datetime.now(UTC)
    stmt = (
        select(BackgroundJob)
        .where(
            BackgroundJob.job_type == JOB_TYPE_SIMULATION,
            BackgroundJob.attempts < BackgroundJob.max_attempts,
            or_(
                (BackgroundJob.status == "QUEUED") & (BackgroundJob.available_at <= now),
                (BackgroundJob.status == "RUNNING")
                & (BackgroundJob.lease_expires_at.is_not(None))
                & (BackgroundJob.lease_expires_at < now),
            ),
        )
        .order_by(BackgroundJob.priority.asc(), BackgroundJob.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = db.scalar(stmt)
    if job is None:
        return None

    job.status = "RUNNING"
    job.locked_by = worker_id
    job.locked_at = now
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    job.attempts = int(job.attempts) + 1
    job.progress_pct = 5.0
    job.progress_message = f"Claimed by worker {worker_id}"

    sim_id_raw = job.payload.get("simulation_id") if isinstance(job.payload, dict) else None
    if sim_id_raw:
        run = db.get(SimulationRun, uuid.UUID(str(sim_id_raw)))
        if run is not None:
            if run.status == "cancelled":
                job.status = "CANCELLED"
                job.completed_at = now
                job.progress_message = "Run already cancelled prior to execution"
                db.commit()
                return None
            run.status = "running"
            run.started_at = run.started_at or now
            run.progress_pct = 5.0

    db.commit()
    db.refresh(job)
    return job


def is_simulation_cancelled(db: Session, simulation_id: uuid.UUID) -> bool:
    """Check current persisted status of simulation run for cooperative cancellation."""
    status_val = db.scalar(
        select(SimulationRun.status).where(SimulationRun.simulation_id == simulation_id)
    )
    return status_val == "cancelled"


def update_job_progress(
    db: Session,
    job_id: uuid.UUID | None,
    simulation_id: uuid.UUID,
    progress_pct: float,
    message: str,
    lease_seconds: int = 300,
) -> None:
    """Renew job lease and persist progress percentage."""
    now = datetime.now(UTC)
    run = db.get(SimulationRun, simulation_id)
    if run is not None and run.status != "cancelled":
        run.progress_pct = float(min(99.0, max(0.0, progress_pct)))
    if job_id is not None:
        job = db.get(BackgroundJob, job_id)
        if job is not None and job.status == "RUNNING":
            job.progress_pct = float(min(99.0, max(0.0, progress_pct)))
            job.progress_message = message
            job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    db.commit()


def persist_simulation_completion(
    db: Session,
    *,
    simulation_id: uuid.UUID,
    job_id: uuid.UUID | None,
    run_updates: dict[str, Any],
    sample_rows: list[dict[str, Any]],
    metric_rows: list[dict[str, Any]],
    event_rows: list[dict[str, Any]],
    batch_size: int = 500,
) -> None:
    """Atomically replace any partial outputs and persist final simulation outputs in batches."""
    now = datetime.now(UTC)
    run = db.get(SimulationRun, simulation_id)
    if run is None:
        raise ValueError(f"SimulationRun {simulation_id} disappeared prior to completion")
    if run.status == "cancelled":
        if job_id is not None:
            job = db.get(BackgroundJob, job_id)
            if job is not None:
                job.status = "CANCELLED"
                job.completed_at = now
        db.commit()
        return

    # Clear prior outputs first so retries never produce duplicate rows
    db.execute(delete(SimulationSample).where(SimulationSample.simulation_id == simulation_id))
    db.execute(delete(SimulationMetric).where(SimulationMetric.simulation_id == simulation_id))
    db.execute(
        delete(SimulationEventWindow).where(SimulationEventWindow.simulation_id == simulation_id)
    )

    for i in range(0, len(sample_rows), batch_size):
        db.execute(insert(SimulationSample), sample_rows[i : i + batch_size])
    for i in range(0, len(metric_rows), batch_size):
        db.execute(insert(SimulationMetric), metric_rows[i : i + batch_size])
    for i in range(0, len(event_rows), batch_size):
        db.execute(insert(SimulationEventWindow), event_rows[i : i + batch_size])

    for k, v in run_updates.items():
        setattr(run, k, v)
    run.status = "completed"
    run.progress_pct = 100.0
    run.completed_at = now
    run.error_summary = None

    if job_id is not None:
        job = db.get(BackgroundJob, job_id)
        if job is not None:
            job.status = "COMPLETED"
            job.progress_pct = 100.0
            job.progress_message = "Simulation completed successfully"
            job.completed_at = now
            job.lease_expires_at = None
            job.result = {
                "simulation_id": str(simulation_id),
                "sample_count": len(sample_rows),
                "event_count": len(event_rows),
                "quality_state": run_updates.get("quality_state"),
            }

    db.commit()


def mark_simulation_failed(
    db: Session,
    *,
    simulation_id: uuid.UUID,
    job_id: uuid.UUID | None,
    quality_state: str,
    error_summary: str,
    retryable: bool = False,
) -> None:
    """Record safe simulation failure or schedule retry when attempts remain."""
    now = datetime.now(UTC)
    job = db.get(BackgroundJob, job_id) if job_id is not None else None
    run = db.get(SimulationRun, simulation_id)

    can_retry = retryable and job is not None and int(job.attempts) < int(job.max_attempts)

    if can_retry and job is not None:
        job.status = "QUEUED"
        job.available_at = now + timedelta(seconds=5 * int(job.attempts))
        job.lease_expires_at = None
        job.error_summary = error_summary
        job.progress_message = f"Retry scheduled after attempt {job.attempts}"
        if run is not None and run.status != "cancelled":
            run.status = "queued"
            run.error_summary = error_summary
    else:
        if job is not None and job.status != "CANCELLED":
            job.status = "FAILED"
            job.completed_at = now
            job.lease_expires_at = None
            job.error_summary = error_summary
            job.progress_message = "Failed"
        if run is not None and run.status != "cancelled":
            run.status = "failed"
            run.quality_state = quality_state
            run.completed_at = now
            run.error_summary = error_summary

    db.commit()


def cancel_simulation_run(
    db: Session, simulation_id: uuid.UUID
) -> tuple[SimulationRun, BackgroundJob | None, bool]:
    """Cancel a queued or running simulation safely. Returns (run, job, cancelled_now)."""
    run = db.get(SimulationRun, simulation_id)
    if run is None:
        raise LookupError(f"Simulation {simulation_id} not found")

    job = db.get(BackgroundJob, run.job_id) if run.job_id is not None else None
    if run.status in ("completed", "failed"):
        return run, job, False

    now = datetime.now(UTC)
    if run.status != "cancelled":
        run.status = "cancelled"
        run.completed_at = now
    if job is not None and job.status in ("QUEUED", "RUNNING"):
        job.status = "CANCELLED"
        job.completed_at = now
        job.lease_expires_at = None
        job.progress_message = "Cancelled by user request"
    db.commit()
    db.refresh(run)
    if job is not None:
        db.refresh(job)
    return run, job, True


def query_simulation_series(
    db: Session,
    *,
    simulation_id: uuid.UUID,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    offset: int = 0,
    limit: int = 500,
    downsample_step: int = 1,
) -> tuple[int, list[SimulationSample]]:
    """Query paginated, time-filtered, and downsampled samples directly in PostgreSQL."""
    filters: list[Any] = [SimulationSample.simulation_id == simulation_id]
    if start_time is not None:
        filters.append(SimulationSample.timestamp_utc >= start_time)
    if end_time is not None:
        filters.append(SimulationSample.timestamp_utc <= end_time)
    if downsample_step > 1:
        filters.append((SimulationSample.sample_index % downsample_step) == 0)

    total = int(db.scalar(select(func.count(SimulationSample.sample_id)).where(*filters)) or 0)
    rows = list(
        db.scalars(
            select(SimulationSample)
            .where(*filters)
            .order_by(SimulationSample.sample_index.asc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return total, rows


def query_simulation_events(
    db: Session,
    simulation_id: uuid.UUID,
    event_type: str | None = None,
) -> list[SimulationEventWindow]:
    """Retrieve transition events and interval windows for a simulation run."""
    filters: list[Any] = [SimulationEventWindow.simulation_id == simulation_id]
    if event_type is not None:
        filters.append(SimulationEventWindow.event_type == event_type)
    return list(
        db.scalars(
            select(SimulationEventWindow)
            .where(*filters)
            .order_by(
                SimulationEventWindow.window_start_utc.asc(), SimulationEventWindow.event_id.asc()
            )
        ).all()
    )


def get_diagnostics_counts(db: Session) -> tuple[int, dict[str, int]]:
    """Return cached horizon profile count and simulation queue status distribution."""
    cached_count = int(db.scalar(select(func.count(TerrainHorizonProfile.horizon_id))) or 0)
    rows = db.execute(
        select(BackgroundJob.status, func.count(BackgroundJob.job_id))
        .where(BackgroundJob.job_type == JOB_TYPE_SIMULATION)
        .group_by(BackgroundJob.status)
    ).all()
    counts = {"QUEUED": 0, "RUNNING": 0, "COMPLETED": 0, "FAILED": 0, "CANCELLED": 0}
    for st, cnt in rows:
        counts[str(st)] = int(cnt)
    return cached_count, counts
