"""Public API endpoints for scientific lunar simulations and Three.js playback series."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.rate_limit import simulation_rate_limiter
from app.db.session import get_db
from app.schemas.simulation import (
    OrbitalTrajectoryOut,
    SimulationCancelOut,
    SimulationCreateIn,
    SimulationCreateOut,
    SimulationEventsOut,
    SimulationSeriesOut,
    SimulationStatusOut,
)
from app.services import simulation_service

router = APIRouter(prefix="/simulations", tags=["Scientific Simulations"])


@router.post(
    "",
    response_model=SimulationCreateOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(simulation_rate_limiter)],
    summary="Queue a new single-site scientific simulation",
    description=(
        "Validates site ID and UTC span against loaded NAIF SPICE kernel coverage, computes adaptive "
        "sampling policy, inspects DEM terrain coverage, and queues a PostgreSQL background job."
    ),
)
def create_simulation(
    payload: SimulationCreateIn,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Create and queue a new SPICE + DEM lunar simulation run."""
    request_id = getattr(request.state, "request_id", None)
    return simulation_service.enqueue_simulation_request(
        db,
        site_id=payload.site_id,
        start_time=payload.start_time,
        duration_seconds=payload.duration_seconds,
        playback_speed=payload.playback_speed,
        request_id=request_id,
        idempotency_key=payload.idempotency_key,
    )


@router.get(
    "/{simulation_id}",
    response_model=SimulationStatusOut,
    status_code=status.HTTP_200_OK,
    summary="Get simulation status, provenance, and summary metrics",
)
def get_simulation_status(
    simulation_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Return execution state, progress, summary statistics, kernel/DEM provenance, and warnings."""
    return simulation_service.get_simulation_status_payload(db, simulation_id)


@router.get(
    "/{simulation_id}/series",
    response_model=SimulationSeriesOut,
    status_code=status.HTTP_200_OK,
    summary="Get paginated or downsampled time series and Three.js geometry contract",
)
def get_simulation_series(
    simulation_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    start_time: Annotated[
        datetime | None, Query(description="Filter samples >= UTC timestamp")
    ] = None,
    end_time: Annotated[
        datetime | None, Query(description="Filter samples <= UTC timestamp")
    ] = None,
    offset: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
    limit: Annotated[int, Query(ge=1, le=2000, description="Max samples returned")] = 500,
    downsample: Annotated[
        int, Query(ge=1, le=100, description="Stride N returning every Nth sample")
    ] = 1,
    include_horizon: Annotated[
        bool, Query(description="Include 360-deg horizon elevation curve for Three.js")
    ] = True,
) -> dict:
    """Retrieve time-tagged astronomical vectors, visibility flags, and terrain horizon profile."""
    return simulation_service.get_simulation_series_payload(
        db,
        simulation_id,
        start_time=start_time,
        end_time=end_time,
        offset=offset,
        limit=limit,
        downsample_step=downsample,
        include_horizon=include_horizon,
    )


@router.get(
    "/{simulation_id}/orbital-trajectory",
    response_model=OrbitalTrajectoryOut,
    status_code=status.HTTP_200_OK,
    summary="Get read-only SPICE ECLIPJ2000 Sun-Earth-Moon trajectory and Moon orientation matrix",
)
def get_simulation_orbital_trajectory(
    simulation_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    samples: Annotated[
        int,
        Query(
            ge=64,
            le=4096,
            description="Number of evenly sampled SPICE trajectory points across the simulation span",
        ),
    ] = 1024,
) -> dict:
    """Compute timestamped SPICE inertial Sun-Earth-Moon vectors for an existing simulation run."""
    return simulation_service.get_simulation_orbital_trajectory_payload(
        db, simulation_id, samples=samples
    )


@router.get(
    "/{simulation_id}/events",
    response_model=SimulationEventsOut,
    status_code=status.HTTP_200_OK,
    summary="Get sunrise/sunset, Earth-rise/set, and concurrent visibility windows",
)
def get_simulation_events(
    simulation_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    event_type: Annotated[
        str | None,
        Query(
            description=(
                "Optional filter: SUNRISE, SUNSET, EARTH_RISE, EARTH_SET, "
                "TOTAL_DARKNESS, SUNLIT, PARTIAL_ILLUMINATION, EARTH_VISIBLE, CONCURRENT_VISIBLE"
            )
        ),
    ] = None,
) -> dict:
    """Retrieve refined transition events and visibility interval windows."""
    return simulation_service.get_simulation_events_payload(
        db, simulation_id, event_type=event_type
    )


@router.post(
    "/{simulation_id}/cancel",
    response_model=SimulationCancelOut,
    status_code=status.HTTP_200_OK,
    summary="Cancel a queued or running simulation job",
)
def cancel_simulation(
    simulation_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Safely cancel an unfinished simulation; returns 409 if already completed or failed."""
    return simulation_service.cancel_simulation_request(db, simulation_id)
