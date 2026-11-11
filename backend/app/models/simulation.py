"""SQLAlchemy models for astronomical simulation runs, samples, horizons, and event windows."""

import uuid
from datetime import datetime

from sqlalchemy import (
    UUID,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SimulationRun(Base):
    """Configuration and execution status of a single-site SPICE/DEM simulation."""

    __tablename__ = "simulation_runs"

    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    site_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("landing_sites.site_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("background_jobs.job_id", ondelete="SET NULL"),
        index=True,
    )
    start_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int] = mapped_column(BigInteger, nullable=False)
    playback_speed: Mapped[float] = mapped_column(Float, default=1.0)
    sample_interval_seconds: Mapped[int] = mapped_column(Integer, default=900)
    ephemeris_source: Mapped[str | None] = mapped_column(Text)
    ephemeris_version: Mapped[str | None] = mapped_column(Text)
    coordinate_frame: Mapped[str] = mapped_column(String(50), default="MOON_ME")
    aberration_policy: Mapped[str] = mapped_column(String(64), default="LT+S")
    terrain_dataset_id: Mapped[str | None] = mapped_column(Text)
    dem_checksum: Mapped[str | None] = mapped_column(String(128))
    algorithm_version: Mapped[str] = mapped_column(String(50), default="v1.0")
    horizon_algorithm_version: Mapped[str | None] = mapped_column(String(50))
    sampling_policy: Mapped[dict | None] = mapped_column(JSONB)
    kernel_manifest: Mapped[dict | None] = mapped_column(JSONB)
    quality_state: Mapped[str] = mapped_column(String(50), default="pending")
    quality_warnings: Mapped[list | None] = mapped_column(JSONB)
    summary_metrics: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(50), default="queued", index=True)
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0)
    error_summary: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("duration_seconds > 0", name="check_sim_duration_positive"),
        CheckConstraint("playback_speed > 0", name="check_sim_playback_speed_positive"),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="check_sim_status",
        ),
        CheckConstraint(
            "quality_state IN ('pending', 'verified_terrain_aware', 'geometric_only', "
            "'partial_dem_coverage', 'insufficient_data', 'kernel_coverage_error', 'failed')",
            name="check_sim_quality_state",
        ),
    )


class SimulationSample(Base):
    """Wide time-series astronomical & terrain-aware visibility sample for playback & Three.js."""

    __tablename__ = "simulation_samples"

    sample_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("simulation_runs.simulation_id", ondelete="CASCADE"),
        nullable=False,
    )
    sample_index: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ephemeris_time: Mapped[float] = mapped_column(Float, nullable=False)
    sun_azimuth_deg: Mapped[float] = mapped_column(Float, nullable=False)
    sun_elevation_deg: Mapped[float] = mapped_column(Float, nullable=False)
    sun_range_km: Mapped[float] = mapped_column(Float, nullable=False)
    earth_azimuth_deg: Mapped[float] = mapped_column(Float, nullable=False)
    earth_elevation_deg: Mapped[float] = mapped_column(Float, nullable=False)
    earth_range_km: Mapped[float] = mapped_column(Float, nullable=False)
    sun_horizon_deg: Mapped[float] = mapped_column(Float, nullable=False)
    earth_horizon_deg: Mapped[float] = mapped_column(Float, nullable=False)
    sun_visibility_status: Mapped[str] = mapped_column(String(32), nullable=False)
    earth_visibility_status: Mapped[str] = mapped_column(String(32), nullable=False)
    concurrent_visible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    sun_dir_moon_x: Mapped[float] = mapped_column(Float, nullable=False)
    sun_dir_moon_y: Mapped[float] = mapped_column(Float, nullable=False)
    sun_dir_moon_z: Mapped[float] = mapped_column(Float, nullable=False)
    earth_dir_moon_x: Mapped[float] = mapped_column(Float, nullable=False)
    earth_dir_moon_y: Mapped[float] = mapped_column(Float, nullable=False)
    earth_dir_moon_z: Mapped[float] = mapped_column(Float, nullable=False)
    subsolar_lat_deg: Mapped[float | None] = mapped_column(Float)
    subsolar_lon_deg: Mapped[float | None] = mapped_column(Float)
    quality_status: Mapped[str] = mapped_column(String(50), nullable=False)

    __table_args__ = (
        UniqueConstraint("simulation_id", "sample_index", name="uq_simulation_samples_run_idx"),
        Index("idx_simulation_samples_run_time", "simulation_id", "timestamp_utc"),
    )


class TerrainHorizonProfile(Base):
    """Cached radial terrain horizon profile theta_hor(psi) keyed by coordinates and DEM version."""

    __tablename__ = "terrain_horizon_profiles"

    horizon_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("landing_sites.site_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cache_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    site_latitude_deg: Mapped[float] = mapped_column(Float, nullable=False)
    site_longitude_deg: Mapped[float] = mapped_column(Float, nullable=False)
    site_elevation_m: Mapped[float | None] = mapped_column(Float)
    observer_height_m: Mapped[float] = mapped_column(Float, nullable=False)
    coordinate_frame: Mapped[str] = mapped_column(String(64), nullable=False)
    dem_asset_id: Mapped[str] = mapped_column(String(120), nullable=False)
    dem_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    dem_resolution_m: Mapped[float] = mapped_column(Float, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(50), nullable=False)
    azimuth_bins: Mapped[int] = mapped_column(Integer, nullable=False)
    azimuths_deg: Mapped[list] = mapped_column(JSONB, nullable=False)
    horizon_elevations_deg: Mapped[list] = mapped_column(JSONB, nullable=False)
    horizon_distances_m: Mapped[list | None] = mapped_column(JSONB)
    uncertainty_deg: Mapped[list | None] = mapped_column(JSONB)
    quality_state: Mapped[str] = mapped_column(String(50), nullable=False)
    coverage_fraction: Mapped[float] = mapped_column(Float, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SimulationMetric(Base):
    """Summary or sampled scalar metrics associated with a simulation run."""

    __tablename__ = "simulation_metrics"

    simulation_metric_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("simulation_runs.simulation_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sample_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    parameter_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    numeric_value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50))
    quality_flag: Mapped[str] = mapped_column(String(50), default="verified")

    __table_args__ = (Index("idx_simulation_metrics_lookup", "simulation_id", "sample_time_utc"),)


class SimulationEventWindow(Base):
    """Discrete transition events and contiguous visibility/illumination windows."""

    __tablename__ = "simulation_event_windows"

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("simulation_runs.simulation_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    window_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(BigInteger, nullable=False)
    confidence_status: Mapped[str] = mapped_column(String(50), default="refined_root")
    method_version: Mapped[str] = mapped_column(String(50), default="v1.0")
    event_metadata: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('SUNRISE', 'SUNSET', 'EARTH_RISE', 'EARTH_SET', 'TOTAL_DARKNESS', "
            "'SUNLIT', 'PARTIAL_ILLUMINATION', 'EARTH_VISIBLE', 'CONCURRENT_VISIBLE')",
            name="check_sim_event_type",
        ),
        Index(
            "idx_simulation_event_windows_lookup",
            "simulation_id",
            "event_type",
            "window_start_utc",
        ),
    )
