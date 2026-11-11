"""SQLAlchemy models for multi-parameter landing site comparisons."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    UUID,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.catalogue import LandingSite
    from app.models.metrics import ParameterDefinition


class ComparisonProfile(Base):
    """Pre-configured or approved mission profile weighting template."""

    __tablename__ = "comparison_profiles"

    profile_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    profile_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    purpose_description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[str] = mapped_column(String(20), default="1.0")

    # Relationships
    parameters: Mapped[list["ComparisonProfileParameter"]] = relationship(
        "ComparisonProfileParameter", back_populates="profile", cascade="all, delete-orphan"
    )


class ComparisonProfileParameter(Base):
    """Weight and evaluation rule for a parameter within a comparison profile."""

    __tablename__ = "comparison_profile_parameters"

    link_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("comparison_profiles.profile_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parameter_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("parameter_definitions.parameter_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    target_value: Mapped[float | None] = mapped_column(Float)
    transformation_key: Mapped[str | None] = mapped_column(String(50))

    # Relationships
    profile: Mapped["ComparisonProfile"] = relationship(
        "ComparisonProfile", back_populates="parameters"
    )
    parameter: Mapped["ParameterDefinition"] = relationship("ParameterDefinition")

    __table_args__ = (
        CheckConstraint("weight >= 0.0 AND weight <= 1.0", name="check_profile_weight_range"),
    )


class ComparisonRun(Base):
    """Execution record for a two-site comparison query with user mission purpose."""

    __tablename__ = "comparison_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    site_a_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("landing_sites.site_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_b_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("landing_sites.site_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_purpose: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_requirements: Mapped[dict | None] = mapped_column(JSONB)
    profile_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("comparison_profiles.profile_id", ondelete="SET NULL")
    )
    algorithm_version: Mapped[str] = mapped_column(String(50), default="v1.0")
    overall_score_a: Mapped[float | None] = mapped_column(Float)
    overall_score_b: Mapped[float | None] = mapped_column(Float)
    overall_winner: Mapped[str | None] = mapped_column(String(50))
    limitations_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(50), default="completed")

    # Relationships
    results: Mapped[list["ComparisonResult"]] = relationship(
        "ComparisonResult", back_populates="run", cascade="all, delete-orphan"
    )
    profile: Mapped[Optional["ComparisonProfile"]] = relationship("ComparisonProfile")
    site_a: Mapped["LandingSite"] = relationship("LandingSite", foreign_keys=[site_a_id])
    site_b: Mapped["LandingSite"] = relationship("LandingSite", foreign_keys=[site_b_id])


class ComparisonResult(Base):
    """Parameter-by-parameter evaluation details and conclusion."""

    __tablename__ = "comparison_results"

    result_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("comparison_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parameter_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("parameter_definitions.parameter_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    value_a: Mapped[float | None] = mapped_column(Float)
    value_b: Mapped[float | None] = mapped_column(Float)
    text_value_a: Mapped[str | None] = mapped_column(Text)
    text_value_b: Mapped[str | None] = mapped_column(Text)
    normalised_a: Mapped[float | None] = mapped_column(Float)
    normalised_b: Mapped[float | None] = mapped_column(Float)
    winner_key: Mapped[str | None] = mapped_column(String(50))
    explanation: Mapped[str | None] = mapped_column(Text)
    data_quality_status: Mapped[str] = mapped_column(String(50), default="verified")

    # Relationships
    run: Mapped["ComparisonRun"] = relationship("ComparisonRun", back_populates="results")
    parameter: Mapped["ParameterDefinition"] = relationship("ParameterDefinition")
