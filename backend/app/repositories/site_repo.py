"""SQLAlchemy repository for landing site queries and mutations."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.catalogue import (
    LandingSite,
    NASARegion,
    SiteContent,
    SiteHistory,
    SiteMedia,
    SiteProCon,
)
from app.models.metrics import ParameterDefinition, SiteMetric
from app.models.provenance import DataSource


def get_sites_paginated(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    region_id: int | None = None,
    catalogue_status: str | None = None,
    search_query: str | None = None,
    sort_by: str = "name",
) -> tuple[list[LandingSite], int]:
    """Retrieve paginated landing sites with eager-loaded regions and primary media."""
    query = select(LandingSite).options(
        joinedload(LandingSite.region),
        selectinload(LandingSite.media),
    )

    if region_id is not None:
        query = query.where(LandingSite.region_id == region_id)

    if catalogue_status is not None:
        query = query.where(LandingSite.catalogue_status == catalogue_status)

    if search_query:
        search_pattern = f"%{search_query.strip()}%"
        query = query.where(
            LandingSite.site_name.ilike(search_pattern)
            | LandingSite.site_code.ilike(search_pattern)
            | LandingSite.site_slug.ilike(search_pattern)
        )

    # Count total matching
    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total_count = db.scalar(count_query) or 0

    # Sorting
    if sort_by == "elevation_asc":
        query = query.order_by(LandingSite.elevation_m.asc().nullslast())
    elif sort_by == "elevation_desc":
        query = query.order_by(LandingSite.elevation_m.desc().nullslast())
    elif sort_by == "updated_at":
        query = query.order_by(LandingSite.updated_at.desc())
    else:
        query = query.order_by(LandingSite.site_name.asc())

    offset = (page - 1) * page_size
    sites = list(db.scalars(query.offset(offset).limit(page_size)).all())

    return sites, total_count


def get_site_by_slug(
    db: Session, site_slug: str, *, published_only: bool = False
) -> LandingSite | None:
    """Retrieve site by unique permanent slug or integer site_id with region and media loaded."""
    stmt = select(LandingSite).options(
        joinedload(LandingSite.region),
        selectinload(LandingSite.media),
        selectinload(LandingSite.content_sections),
    )
    if site_slug.isdigit():
        stmt = stmt.where(
            or_(LandingSite.site_slug == site_slug, LandingSite.site_id == int(site_slug))
        )
    else:
        stmt = stmt.where(LandingSite.site_slug == site_slug)
    if published_only:
        stmt = stmt.where(LandingSite.catalogue_status == "published")
    return db.scalar(stmt)


def get_site_id_by_slug(db: Session, site_slug: str, *, published_only: bool = False) -> int | None:
    """Resolve primary site_id from permanent slug or integer ID without loading relations."""
    stmt = select(LandingSite.site_id)
    if site_slug.isdigit():
        stmt = stmt.where(
            or_(LandingSite.site_slug == site_slug, LandingSite.site_id == int(site_slug))
        )
    else:
        stmt = stmt.where(LandingSite.site_slug == site_slug)
    if published_only:
        stmt = stmt.where(LandingSite.catalogue_status == "published")
    return db.scalar(stmt)


def get_site_by_code(db: Session, site_code: str) -> LandingSite | None:
    """Retrieve site by stable project site code."""
    stmt = select(LandingSite).where(LandingSite.site_code == site_code)
    return db.scalar(stmt)


def get_site_by_id(db: Session, site_id: int) -> LandingSite | None:
    """Retrieve site by primary key."""
    return db.get(LandingSite, site_id)


def get_site_sections(
    db: Session, site_id: int, section_key: str | None = None
) -> list[SiteContent]:
    """Retrieve uncapped narrative content sections for a site."""
    stmt = select(SiteContent).where(SiteContent.site_id == site_id)
    if section_key:
        stmt = stmt.where(SiteContent.section_key == section_key)
    stmt = stmt.order_by(SiteContent.display_order.asc(), SiteContent.content_id.asc())
    return list(db.scalars(stmt).all())


def get_site_pros_cons(db: Session, site_id: int) -> list[tuple[SiteProCon, str | None]]:
    """Retrieve structured pros and cons joined with optional source citation."""
    stmt = (
        select(SiteProCon, DataSource.title.label("source_title"))
        .outerjoin(DataSource, SiteProCon.source_id == DataSource.source_id)
        .where(SiteProCon.site_id == site_id)
        .order_by(
            SiteProCon.point_type.desc(), SiteProCon.display_order.asc(), SiteProCon.point_id.asc()
        )
    )
    return list(db.execute(stmt).all())


def get_site_metrics(
    db: Session, site_id: int
) -> list[tuple[SiteMetric, ParameterDefinition, str | None, str | None, str | None]]:
    """Retrieve scientific measurements joined with parameter definition and source."""
    stmt = (
        select(
            SiteMetric,
            ParameterDefinition,
            DataSource.citation_text,
            DataSource.title,
            DataSource.source_url,
        )
        .join(ParameterDefinition, SiteMetric.parameter_id == ParameterDefinition.parameter_id)
        .outerjoin(DataSource, SiteMetric.source_id == DataSource.source_id)
        .where(SiteMetric.site_id == site_id)
        .order_by(ParameterDefinition.parameter_key.asc())
    )
    return list(db.execute(stmt).all())


def get_site_media(db: Session, site_id: int) -> list[SiteMedia]:
    """Retrieve gallery assets for a site ordered by display_order."""
    stmt = (
        select(SiteMedia)
        .where(SiteMedia.site_id == site_id)
        .order_by(
            SiteMedia.is_primary.desc(), SiteMedia.display_order.asc(), SiteMedia.media_id.asc()
        )
    )
    return list(db.scalars(stmt).all())


def get_site_history(db: Session, site_id: int) -> list[SiteHistory]:
    """Retrieve chronological history events."""
    stmt = (
        select(SiteHistory)
        .where(SiteHistory.site_id == site_id)
        .order_by(SiteHistory.event_date.asc().nullslast(), SiteHistory.display_order.asc())
    )
    return list(db.scalars(stmt).all())


def create_site(db: Session, site_data: dict) -> LandingSite:
    """Create a new landing site record."""
    site = LandingSite(**site_data)
    db.add(site)
    db.flush()
    return site


def update_site(db: Session, site: LandingSite, update_data: dict) -> LandingSite:
    """Update landing site fields."""
    for key, value in update_data.items():
        if hasattr(site, key):
            setattr(site, key, value)
    db.flush()
    return site


def create_section(db: Session, section_data: dict) -> SiteContent:
    """Create a content section."""
    section = SiteContent(**section_data)
    db.add(section)
    db.flush()
    return section


def create_pro_con(db: Session, procon_data: dict) -> SiteProCon:
    """Create a pro or con point."""
    point = SiteProCon(**procon_data)
    db.add(point)
    db.flush()
    return point


def list_regions(db: Session) -> list[NASARegion]:
    """List all NASA exploration regions ordered alphabetically."""
    return list(db.scalars(select(NASARegion).order_by(NASARegion.region_name.asc())).all())


def get_section_by_id(db: Session, content_id: int) -> SiteContent | None:
    """Retrieve narrative section by primary key."""
    return db.get(SiteContent, content_id)


def update_section(db: Session, section: SiteContent, update_data: dict) -> SiteContent:
    """Apply partial updates to a landing site narrative section."""
    for key, value in update_data.items():
        if hasattr(section, key):
            setattr(section, key, value)
    db.flush()
    return section


def delete_section(db: Session, section: SiteContent) -> None:
    """Delete a landing site narrative section."""
    db.delete(section)
    db.flush()


def get_pro_con_by_id(db: Session, point_id: int) -> SiteProCon | None:
    """Retrieve pro/con evaluation point by primary key."""
    return db.get(SiteProCon, point_id)


def update_pro_con(db: Session, point: SiteProCon, update_data: dict) -> SiteProCon:
    """Apply partial updates to a pro/con entry."""
    for key, value in update_data.items():
        if hasattr(point, key):
            setattr(point, key, value)
    db.flush()
    return point


def delete_pro_con(db: Session, point: SiteProCon) -> None:
    """Delete a pro/con entry."""
    db.delete(point)
    db.flush()


def get_history_by_id(db: Session, history_id: int) -> SiteHistory | None:
    """Retrieve a mission/discovery history entry by primary key."""
    return db.get(SiteHistory, history_id)


def create_history(db: Session, history_data: dict) -> SiteHistory:
    """Create a chronological history milestone."""
    entry = SiteHistory(**history_data)
    db.add(entry)
    db.flush()
    return entry


def update_history(db: Session, entry: SiteHistory, update_data: dict) -> SiteHistory:
    """Apply partial updates to a chronological history milestone."""
    for key, value in update_data.items():
        if hasattr(entry, key):
            setattr(entry, key, value)
    db.flush()
    return entry


def delete_history(db: Session, entry: SiteHistory) -> None:
    """Delete a chronological history milestone."""
    db.delete(entry)
    db.flush()


def upsert_site_metric(
    db: Session,
    *,
    site_id: int,
    parameter_id: int,
    metric_data: dict,
) -> SiteMetric:
    """Insert or update the authoritative baseline measurement for a (site, parameter) pair."""
    existing = db.scalar(
        select(SiteMetric).where(
            SiteMetric.site_id == site_id,
            SiteMetric.parameter_id == parameter_id,
        )
    )
    if existing is None:
        metric = SiteMetric(site_id=site_id, parameter_id=parameter_id, **metric_data)
        db.add(metric)
        db.flush()
        return metric
    for key, value in metric_data.items():
        if hasattr(existing, key):
            setattr(existing, key, value)
    db.flush()
    return existing


def delete_site(db: Session, site: LandingSite) -> None:
    """Delete a non-published landing site and cascading child records."""
    db.delete(site)
    db.flush()
