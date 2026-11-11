"""Pydantic v2 schemas for Phase 4 scientific simulations and Three.js data contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings


class SimulationCreateIn(BaseModel):
    """Public simulation request accepting strictly single-site ID, timing, and playback speed."""

    site_id: int = Field(..., gt=0, description="Database ID of registered landing site")
    start_time: datetime = Field(..., description="Simulation start timestamp (ISO 8601 UTC)")
    duration_seconds: int = Field(
        ...,
        gt=0,
        le=settings.SIM_MAX_DURATION_SECONDS,
        description="Total physical duration in seconds",
    )
    playback_speed: float = Field(
        default=1.0,
        gt=0.0,
        le=100000.0,
        description="Visual playback multiplier for UI timeline (never affects physics)",
    )
    idempotency_key: str | None = Field(
        default=None,
        min_length=4,
        max_length=128,
        description="Optional client idempotency token preventing duplicate queued runs",
    )

    @field_validator("start_time")
    @classmethod
    def ensure_utc(cls, value: datetime) -> datetime:
        """Normalize naive timestamps to UTC; preserve explicit timezone offset."""
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class SamplingPolicyOut(BaseModel):
    """Adaptive coarse-plus-refinement sampling configuration computed for a run."""

    coarse_interval_seconds: int
    max_coarse_samples: int
    transition_tolerance_seconds: float
    adaptive_refinement_enabled: bool = True
    estimated_coarse_samples: int
    horizon_max_radius_m: float
    horizon_azimuth_bins: int
    observer_height_m: float
    precision_note: str


class SimulationCreateOut(BaseModel):
    """Response returned immediately upon queueing a background simulation job."""

    simulation_id: UUID
    job_id: UUID
    site_id: int
    site_name: str
    site_slug: str
    status: str
    quality_state: str
    start_time_utc: datetime
    end_time_utc: datetime
    duration_seconds: int
    playback_speed: float
    sampling_policy: SamplingPolicyOut
    data_coverage_warnings: list[str] = Field(default_factory=list)
    created_at: datetime


class SiteSimulationSummaryOut(BaseModel):
    """Site coordinates and Moon-fixed Cartesian anchor for simulation inspection & Three.js."""

    site_id: int
    site_code: str
    site_slug: str
    site_name: str
    latitude_deg: float
    longitude_deg: float
    elevation_m: float | None = None
    coordinate_reference: str
    cartesian_moon_me_km: tuple[float, float, float]


class SimulationStatusOut(BaseModel):
    """Comprehensive simulation metadata, status, progress, provenance, and summary metrics."""

    simulation_id: UUID
    job_id: UUID | None = None
    status: str
    progress_pct: float
    progress_message: str | None = None
    quality_state: str
    quality_warnings: list[str] = Field(default_factory=list)
    site: SiteSimulationSummaryOut
    start_time_utc: datetime
    end_time_utc: datetime | None = None
    duration_seconds: int
    playback_speed: float
    coordinate_frame: str
    resolved_frame: str | None = None
    aberration_policy: str
    algorithm_version: str
    horizon_algorithm_version: str | None = None
    sampling_policy: dict[str, Any] = Field(default_factory=dict)
    kernel_manifest: dict[str, Any] = Field(default_factory=dict)
    dem_metadata: dict[str, Any] = Field(default_factory=dict)
    summary_metrics: dict[str, Any] | None = None
    limitations_disclaimers: list[str] = Field(default_factory=list)
    error_summary: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class CelestialBodySampleOut(BaseModel):
    """Topocentric sky angles, terrain horizon obstruction, and 3D unit vector in MOON_ME."""

    azimuth_deg: float = Field(..., description="Degrees [0, 360) CW from local North via East")
    elevation_deg: float = Field(..., description="Degrees [-90, 90] above local horizon plane")
    range_km: float = Field(..., description="Topocentric range from observer site in km")
    horizon_deg: float = Field(..., description="Interpolated DEM terrain horizon elevation (deg)")
    dir_moon_me: tuple[float, float, float] = Field(
        ..., description="Unit direction vector in Moon-fixed MOON_ME frame"
    )
    visibility_status: str


class SimulationSampleOut(BaseModel):
    """Single time-tagged keyframe for Three.js visualization and analysis charts."""

    sample_index: int
    timestamp_utc: datetime
    ephemeris_time: float
    elapsed_seconds: float
    sun: CelestialBodySampleOut
    earth: CelestialBodySampleOut
    concurrent_visible: bool
    subsolar_lat_deg: float | None = None
    subsolar_lon_deg: float | None = None
    quality_status: str


class HorizonCurveOut(BaseModel):
    """Compact 360-degree terrain skyline array for frontend horizon overlay."""

    azimuth_bins: int
    azimuths_deg: list[float]
    horizon_elevations_deg: list[float]
    horizon_distances_m: list[float] | None = None
    uncertainty_deg: list[float] | None = None
    quality_state: str
    dem_asset_id: str | None = None


class SimulationSeriesOut(BaseModel):
    """Paginated/windowed and optionally downsampled time series for Three.js scene driving."""

    simulation_id: UUID
    status: str
    quality_state: str
    playback_speed: float
    site: SiteSimulationSummaryOut
    coordinate_contract: dict[str, str]
    units: dict[str, str]
    horizon_profile: HorizonCurveOut | None = None
    total_samples_available: int
    returned_samples: int
    offset: int
    limit: int
    downsample_step: int
    samples: list[SimulationSampleOut] = Field(default_factory=list)


class SimulationEventOut(BaseModel):
    """Discrete rise/set transition event or continuous visibility window."""

    event_id: int
    event_type: str
    window_start_utc: datetime
    window_end_utc: datetime
    duration_seconds: int
    confidence_status: str
    method_version: str
    event_metadata: dict[str, Any] = Field(default_factory=dict)


class SimulationEventsOut(BaseModel):
    """Collection of discrete transition events and visibility windows for a simulation run."""

    simulation_id: UUID
    status: str
    quality_state: str
    total_events: int
    events: list[SimulationEventOut] = Field(default_factory=list)


class SimulationCancelOut(BaseModel):
    """Cancellation acknowledgment payload."""

    simulation_id: UUID
    job_id: UUID | None = None
    status: str
    message: str


class AdminSiteCoverageEntry(BaseModel):
    """DEM coverage audit entry for a registered landing site."""

    site_id: int
    site_slug: str
    site_name: str
    latitude_deg: float
    longitude_deg: float
    coverage_status: str
    selected_dem_asset_id: str | None = None
    resolution_m: float | None = None
    min_edge_margin_km: float | None = None


class AdminSimulationDiagnosticsOut(BaseModel):
    """Administrative diagnostics for SPICE kernels, DEM assets, horizon cache, and worker queue."""

    spice_ready: bool
    spice_error: str | None = None
    spice_manifest: dict[str, Any] = Field(default_factory=dict)
    available_frames: dict[str, int] = Field(default_factory=dict)
    dem_assets_count: int
    dem_assets: list[dict[str, Any]] = Field(default_factory=list)
    site_dem_coverage: list[AdminSiteCoverageEntry] = Field(default_factory=list)
    cached_horizon_profiles_count: int
    worker_queue_counts: dict[str, int] = Field(default_factory=dict)
