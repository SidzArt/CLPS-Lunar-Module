"""SQLAlchemy models for scientific parameters, site metrics, and time series."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ParameterDefinition(Base):
    """Dictionary of scientific and operational parameters for lunar landing sites."""

    __tablename__ = "parameter_definitions"

    parameter_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parameter_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(50))
    value_type: Mapped[str] = mapped_column(String(50), default="numeric")
    comparison_direction: Mapped[str] = mapped_column(String(50), default="higher")
    target_value: Mapped[float | None] = mapped_column(Float)
    is_comparable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_time_dependent: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_min: Mapped[float | None] = mapped_column(Float)
    validation_max: Mapped[float | None] = mapped_column(Float)
    benchmark_min: Mapped[float | None] = mapped_column(Float)
    benchmark_max: Mapped[float | None] = mapped_column(Float)
    tolerance: Mapped[float | None] = mapped_column(Float)
    methodology_note: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    __table_args__ = (
        CheckConstraint(
            "comparison_direction IN ('higher', 'lower', 'target', 'context', 'informational')",
            name="check_param_comparison_direction",
        ),
        CheckConstraint(
            "value_type IN ('numeric', 'boolean', 'categorical', 'text')",
            name="check_param_value_type",
        ),
    )


class SiteMetric(Base):
    """Static or baseline scientific measurements for a specific landing site."""

    __tablename__ = "site_metrics"

    site_metric_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("landing_sites.site_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parameter_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("parameter_definitions.parameter_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    numeric_value: Mapped[float | None] = mapped_column(Float)
    text_value: Mapped[str | None] = mapped_column(Text)
    unit_override: Mapped[str | None] = mapped_column(String(50))
    uncertainty_value: Mapped[float | None] = mapped_column(Float)
    methodology: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("data_sources.source_id", ondelete="SET NULL")
    )
    data_quality_status: Mapped[str] = mapped_column(String(50), default="verified")
    dataset_version: Mapped[str | None] = mapped_column(String(100))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("idx_site_metrics_site_param", "site_id", "parameter_id"),)


class MetricObservation(Base):
    """Time-windowed observations or ephemeris-derived historical samples."""

    __tablename__ = "metric_observations"

    observation_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("landing_sites.site_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parameter_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("parameter_definitions.parameter_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sample_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    numeric_value: Mapped[float] = mapped_column(Float, nullable=False)
    uncertainty_value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(50))
    method_key: Mapped[str | None] = mapped_column(String(100))
    source_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("data_sources.source_id", ondelete="SET NULL")
    )
    calculation_version: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_metric_observations_lookup", "site_id", "parameter_id", "sample_time"),
    )
