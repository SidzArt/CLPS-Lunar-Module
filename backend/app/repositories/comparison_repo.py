"""SQLAlchemy repository for landing site comparisons and metric lookups."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.catalogue import LandingSite
from app.models.comparison import (
    ComparisonProfile,
    ComparisonProfileParameter,
    ComparisonResult,
    ComparisonRun,
)
from app.models.metrics import ParameterDefinition, SiteMetric


def get_profile_by_key(db: Session, profile_key: str) -> ComparisonProfile | None:
    """Retrieve an active comparison profile by its unique key, with loaded parameters."""
    stmt = (
        select(ComparisonProfile)
        .options(
            joinedload(ComparisonProfile.parameters).joinedload(
                ComparisonProfileParameter.parameter
            )
        )
        .where(
            ComparisonProfile.profile_key == profile_key,
            ComparisonProfile.is_active == True,
        )
    )
    return db.scalars(stmt).unique().first()


def get_profile_by_id(db: Session, profile_id: int) -> ComparisonProfile | None:
    """Retrieve an active comparison profile by its primary key."""
    stmt = (
        select(ComparisonProfile)
        .options(
            joinedload(ComparisonProfile.parameters).joinedload(
                ComparisonProfileParameter.parameter
            )
        )
        .where(
            ComparisonProfile.profile_id == profile_id,
            ComparisonProfile.is_active == True,
        )
    )
    return db.scalars(stmt).unique().first()


def list_active_profiles(db: Session) -> list[ComparisonProfile]:
    """List all active comparison profiles with their parameter rules."""
    stmt = (
        select(ComparisonProfile)
        .options(
            joinedload(ComparisonProfile.parameters).joinedload(
                ComparisonProfileParameter.parameter
            )
        )
        .where(ComparisonProfile.is_active == True)
        .order_by(ComparisonProfile.profile_id)
    )
    return list(db.scalars(stmt).unique().all())


def get_parameter_definitions(
    db: Session, keys: list[str] | None = None
) -> list[ParameterDefinition]:
    """Retrieve active parameter definitions, optionally filtered by key."""
    stmt = select(ParameterDefinition).where(ParameterDefinition.is_active == True)
    if keys:
        stmt = stmt.where(ParameterDefinition.parameter_key.in_(keys))
    stmt = stmt.order_by(ParameterDefinition.parameter_id)
    return list(db.scalars(stmt).all())


def get_site_metrics_map(db: Session, site_ids: list[int]) -> dict[int, dict[str, SiteMetric]]:
    """Retrieve all metrics for specified sites mapped as {site_id: {parameter_key: SiteMetric}}."""
    stmt = (
        select(SiteMetric)
        .join(ParameterDefinition, SiteMetric.parameter_id == ParameterDefinition.parameter_id)
        .where(SiteMetric.site_id.in_(site_ids))
    )
    metrics = db.scalars(stmt).all()

    # Pre-fetch all parameter definitions to map by key efficiently
    params = {
        p.parameter_id: p.parameter_key for p in db.scalars(select(ParameterDefinition)).all()
    }

    site_map: dict[int, dict[str, SiteMetric]] = {sid: {} for sid in site_ids}
    for m in metrics:
        pkey = params.get(m.parameter_id)
        if pkey:
            site_map[m.site_id][pkey] = m

    return site_map


def get_sites_by_ids(db: Session, site_ids: list[int]) -> dict[int, LandingSite]:
    """Retrieve landing site records mapped by site_id."""
    stmt = select(LandingSite).where(LandingSite.site_id.in_(site_ids))
    sites = db.scalars(stmt).all()
    return {s.site_id: s for s in sites}


def create_comparison_run(
    db: Session,
    *,
    run_id: uuid.UUID,
    site_a_id: int,
    site_b_id: int,
    user_purpose: str,
    parsed_requirements: dict[str, Any] | None,
    profile_id: int | None,
    algorithm_version: str = "v1.0",
    overall_score_a: float | None = None,
    overall_score_b: float | None = None,
    overall_winner: str | None = None,
    limitations_note: str | None = None,
    status: str = "completed",
) -> ComparisonRun:
    """Persist a comparison execution run record."""
    run = ComparisonRun(
        run_id=run_id,
        site_a_id=site_a_id,
        site_b_id=site_b_id,
        user_purpose=user_purpose,
        parsed_requirements=parsed_requirements,
        profile_id=profile_id,
        algorithm_version=algorithm_version,
        overall_score_a=overall_score_a,
        overall_score_b=overall_score_b,
        overall_winner=overall_winner,
        limitations_note=limitations_note,
        status=status,
    )
    db.add(run)
    db.flush()
    return run


def bulk_create_comparison_results(db: Session, results: list[dict[str, Any]]) -> None:
    """Bulk insert detailed parameter comparison result rows."""
    objects = [ComparisonResult(**res) for res in results]
    db.add_all(objects)
    db.flush()
