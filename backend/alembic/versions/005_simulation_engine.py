"""Extend simulation_runs, simulation_event_windows, and background_jobs; add simulation_samples and terrain_horizon_profiles.

Revision ID: 005_simulation_engine
Revises: 004_comparison_profiles
Create Date: 2026-11-11 09:45:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "005_simulation_engine"
down_revision: str | None = "004_comparison_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Extend background_jobs for worker leases, progress tracking, and idempotency
    op.add_column(
        "background_jobs",
        sa.Column("progress_pct", sa.Float(), nullable=False, server_default="0.0"),
    )
    op.add_column(
        "background_jobs",
        sa.Column("progress_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "background_jobs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "background_jobs",
        sa.Column("idempotency_key", sa.String(128), nullable=True),
    )
    op.create_unique_constraint(
        "uq_background_jobs_idempotency_key",
        "background_jobs",
        ["idempotency_key"],
    )

    # 2. Extend simulation_runs with scientific provenance, quality state, and job linkage
    op.add_column(
        "simulation_runs",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_simulation_runs_job_id",
        "simulation_runs",
        "background_jobs",
        ["job_id"],
        ["job_id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_simulation_runs_job_id", "simulation_runs", ["job_id"])

    op.add_column(
        "simulation_runs",
        sa.Column("end_time_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "simulation_runs",
        sa.Column("progress_pct", sa.Float(), nullable=False, server_default="0.0"),
    )
    op.add_column(
        "simulation_runs",
        sa.Column("aberration_policy", sa.String(64), nullable=False, server_default="'LT+S'"),
    )
    op.add_column(
        "simulation_runs",
        sa.Column("dem_checksum", sa.String(128), nullable=True),
    )
    op.add_column(
        "simulation_runs",
        sa.Column("horizon_algorithm_version", sa.String(50), nullable=True),
    )
    op.add_column(
        "simulation_runs",
        sa.Column("sampling_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "simulation_runs",
        sa.Column("kernel_manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "simulation_runs",
        sa.Column("quality_state", sa.String(50), nullable=False, server_default="'pending'"),
    )
    op.create_check_constraint(
        "check_sim_quality_state",
        "simulation_runs",
        "quality_state IN ('pending', 'verified_terrain_aware', 'geometric_only', "
        "'partial_dem_coverage', 'insufficient_data', 'kernel_coverage_error', 'failed')",
    )
    op.add_column(
        "simulation_runs",
        sa.Column("quality_warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "simulation_runs",
        sa.Column("summary_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "simulation_runs",
        sa.Column("error_summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "simulation_runs",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "simulation_runs",
        sa.Column("request_id", sa.String(64), nullable=True),
    )

    # 3. Expand simulation_event_windows for visibility intervals and provenance
    op.drop_constraint(
        "check_sim_event_type",
        "simulation_event_windows",
        type_="check",
    )
    op.create_check_constraint(
        "check_sim_event_type",
        "simulation_event_windows",
        "event_type IN ('SUNRISE', 'SUNSET', 'EARTH_RISE', 'EARTH_SET', 'TOTAL_DARKNESS', "
        "'SUNLIT', 'PARTIAL_ILLUMINATION', 'EARTH_VISIBLE', 'CONCURRENT_VISIBLE')",
    )
    op.add_column(
        "simulation_event_windows",
        sa.Column(
            "confidence_status", sa.String(50), nullable=False, server_default="'refined_root'"
        ),
    )
    op.add_column(
        "simulation_event_windows",
        sa.Column("method_version", sa.String(50), nullable=False, server_default="'v1.0'"),
    )
    op.add_column(
        "simulation_event_windows",
        sa.Column("event_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        "idx_simulation_event_windows_lookup",
        "simulation_event_windows",
        ["simulation_id", "event_type", "window_start_utc"],
    )

    # 4. Create simulation_samples table for wide structured time-series + Three.js keyframes
    op.create_table(
        "simulation_samples",
        sa.Column("sample_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("simulation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sample_index", sa.Integer(), nullable=False),
        sa.Column("timestamp_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ephemeris_time", sa.Float(), nullable=False),
        sa.Column("sun_azimuth_deg", sa.Float(), nullable=False),
        sa.Column("sun_elevation_deg", sa.Float(), nullable=False),
        sa.Column("sun_range_km", sa.Float(), nullable=False),
        sa.Column("earth_azimuth_deg", sa.Float(), nullable=False),
        sa.Column("earth_elevation_deg", sa.Float(), nullable=False),
        sa.Column("earth_range_km", sa.Float(), nullable=False),
        sa.Column("sun_horizon_deg", sa.Float(), nullable=False),
        sa.Column("earth_horizon_deg", sa.Float(), nullable=False),
        sa.Column("sun_visibility_status", sa.String(32), nullable=False),
        sa.Column("earth_visibility_status", sa.String(32), nullable=False),
        sa.Column("concurrent_visible", sa.Boolean(), nullable=False),
        sa.Column("sun_dir_moon_x", sa.Float(), nullable=False),
        sa.Column("sun_dir_moon_y", sa.Float(), nullable=False),
        sa.Column("sun_dir_moon_z", sa.Float(), nullable=False),
        sa.Column("earth_dir_moon_x", sa.Float(), nullable=False),
        sa.Column("earth_dir_moon_y", sa.Float(), nullable=False),
        sa.Column("earth_dir_moon_z", sa.Float(), nullable=False),
        sa.Column("subsolar_lat_deg", sa.Float(), nullable=True),
        sa.Column("subsolar_lon_deg", sa.Float(), nullable=True),
        sa.Column("quality_status", sa.String(50), nullable=False),
        sa.ForeignKeyConstraint(
            ["simulation_id"],
            ["simulation_runs.simulation_id"],
            name="fk_simulation_samples_simulation_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("sample_id"),
        sa.UniqueConstraint("simulation_id", "sample_index", name="uq_simulation_samples_run_idx"),
    )
    op.create_index(
        "idx_simulation_samples_run_time",
        "simulation_samples",
        ["simulation_id", "timestamp_utc"],
    )

    # 5. Create terrain_horizon_profiles cache table
    op.create_table(
        "terrain_horizon_profiles",
        sa.Column("horizon_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("site_id", sa.BigInteger(), nullable=False),
        sa.Column("cache_key", sa.String(128), nullable=False),
        sa.Column("site_latitude_deg", sa.Float(), nullable=False),
        sa.Column("site_longitude_deg", sa.Float(), nullable=False),
        sa.Column("site_elevation_m", sa.Float(), nullable=True),
        sa.Column("observer_height_m", sa.Float(), nullable=False),
        sa.Column("coordinate_frame", sa.String(64), nullable=False),
        sa.Column("dem_asset_id", sa.String(120), nullable=False),
        sa.Column("dem_checksum", sa.String(128), nullable=False),
        sa.Column("dem_resolution_m", sa.Float(), nullable=False),
        sa.Column("algorithm_version", sa.String(50), nullable=False),
        sa.Column("azimuth_bins", sa.Integer(), nullable=False),
        sa.Column("azimuths_deg", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "horizon_elevations_deg", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("horizon_distances_m", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("uncertainty_deg", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("quality_state", sa.String(50), nullable=False),
        sa.Column("coverage_fraction", sa.Float(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["site_id"],
            ["landing_sites.site_id"],
            name="fk_terrain_horizon_site_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("horizon_id"),
        sa.UniqueConstraint("cache_key", name="uq_terrain_horizon_cache_key"),
    )
    op.create_index("idx_terrain_horizon_site_id", "terrain_horizon_profiles", ["site_id"])


def downgrade() -> None:
    op.drop_index("idx_terrain_horizon_site_id", table_name="terrain_horizon_profiles")
    op.drop_table("terrain_horizon_profiles")

    op.drop_index("idx_simulation_samples_run_time", table_name="simulation_samples")
    op.drop_table("simulation_samples")

    op.drop_index("idx_simulation_event_windows_lookup", table_name="simulation_event_windows")
    op.drop_column("simulation_event_windows", "event_metadata")
    op.drop_column("simulation_event_windows", "method_version")
    op.drop_column("simulation_event_windows", "confidence_status")
    op.drop_constraint("check_sim_event_type", "simulation_event_windows", type_="check")
    op.create_check_constraint(
        "check_sim_event_type",
        "simulation_event_windows",
        "event_type IN ('SUNRISE', 'SUNSET', 'EARTH_RISE', 'EARTH_SET', 'TOTAL_DARKNESS')",
    )

    op.drop_column("simulation_runs", "request_id")
    op.drop_column("simulation_runs", "started_at")
    op.drop_column("simulation_runs", "error_summary")
    op.drop_column("simulation_runs", "summary_metrics")
    op.drop_column("simulation_runs", "quality_warnings")
    op.drop_constraint("check_sim_quality_state", "simulation_runs", type_="check")
    op.drop_column("simulation_runs", "quality_state")
    op.drop_column("simulation_runs", "kernel_manifest")
    op.drop_column("simulation_runs", "sampling_policy")
    op.drop_column("simulation_runs", "horizon_algorithm_version")
    op.drop_column("simulation_runs", "dem_checksum")
    op.drop_column("simulation_runs", "aberration_policy")
    op.drop_column("simulation_runs", "progress_pct")
    op.drop_column("simulation_runs", "end_time_utc")
    op.drop_index("idx_simulation_runs_job_id", table_name="simulation_runs")
    op.drop_constraint("fk_simulation_runs_job_id", "simulation_runs", type_="foreignkey")
    op.drop_column("simulation_runs", "job_id")

    op.drop_constraint("uq_background_jobs_idempotency_key", "background_jobs", type_="unique")
    op.drop_column("background_jobs", "idempotency_key")
    op.drop_column("background_jobs", "lease_expires_at")
    op.drop_column("background_jobs", "progress_message")
    op.drop_column("background_jobs", "progress_pct")
