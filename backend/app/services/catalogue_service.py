"""Service orchestrating landing site catalogue retrieval and section assembly."""

from sqlalchemy.orm import Session

from app.repositories import site_repo
from app.schemas.catalogue import (
    PaginatedResponse,
    SiteCardOut,
    SiteDetailOut,
    SiteHistoryOut,
    SiteMediaOut,
    SiteMetricOut,
    SiteProConOut,
    SiteSectionOut,
)


def get_site_cards(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    region_id: int | None = None,
    catalogue_status: str | None = "published",
    search_query: str | None = None,
    sort_by: str = "name",
) -> PaginatedResponse[SiteCardOut]:
    """Retrieve paginated landing site cards for exploration views."""
    sites, total = site_repo.get_sites_paginated(
        db=db,
        page=page,
        page_size=page_size,
        region_id=region_id,
        catalogue_status=catalogue_status,
        search_query=search_query,
        sort_by=sort_by,
    )

    items = []
    for s in sites:
        primary_thumb = None
        for m in s.media:
            if m.is_primary and m.thumbnail_path:
                primary_thumb = f"/storage/{m.thumbnail_path}"
                break
        if not primary_thumb and s.media and s.media[0].thumbnail_path:
            primary_thumb = f"/storage/{s.media[0].thumbnail_path}"

        items.append(
            SiteCardOut(
                site_id=s.site_id,
                site_slug=s.site_slug,
                site_code=s.site_code,
                site_name=s.site_name,
                region_id=s.region_id,
                region_name=s.region.region_name if s.region else None,
                latitude_deg=float(s.latitude_deg),
                longitude_deg=float(s.longitude_deg),
                elevation_m=s.elevation_m,
                terrain_type=s.terrain_type,
                overview_summary=s.overview_summary,
                catalogue_status=s.catalogue_status,
                primary_thumbnail=primary_thumb,
                updated_at=s.updated_at,
            )
        )

    has_more = (page * page_size) < total

    return PaginatedResponse[SiteCardOut](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


def get_site_detail(
    db: Session, site_slug: str, *, published_only: bool = True
) -> SiteDetailOut | None:
    """Retrieve full profile details for an individual site by unique slug."""
    site = site_repo.get_site_by_slug(db, site_slug, published_only=published_only)
    if not site:
        return None

    primary_url = None
    for m in site.media:
        if m.is_primary and m.file_path:
            primary_url = f"/storage/{m.file_path}"
            break
    if not primary_url and site.media:
        primary_url = f"/storage/{site.media[0].file_path}"

    available_sections = list({cs.section_key for cs in site.content_sections})

    return SiteDetailOut(
        site_id=site.site_id,
        site_slug=site.site_slug,
        site_code=site.site_code,
        site_name=site.site_name,
        alternate_names=site.alternate_names,
        region_id=site.region_id,
        region_name=site.region.region_name if site.region else None,
        region_code=site.region.region_code if site.region else None,
        latitude_deg=float(site.latitude_deg),
        longitude_deg=float(site.longitude_deg),
        elevation_m=site.elevation_m,
        terrain_type=site.terrain_type,
        overview_summary=site.overview_summary,
        catalogue_status=site.catalogue_status,
        coordinate_reference=site.coordinate_reference,
        seo_title=site.seo_title or f"{site.site_name} Lunar Landing Site Dossier",
        seo_meta_description=site.seo_meta_description or site.overview_summary,
        og_image_url=site.og_image_url or primary_url,
        primary_image_url=primary_url,
        available_sections=available_sections,
        created_at=site.created_at,
        updated_at=site.updated_at,
    )


def resolve_site_id_by_slug(
    db: Session, site_slug: str, *, published_only: bool = True
) -> int | None:
    """Resolve primary site_id by slug without loading full detail relationships."""
    return site_repo.get_site_id_by_slug(db, site_slug, published_only=published_only)


def get_site_sections(
    db: Session,
    site_slug: str,
    section_key: str | None = None,
    *,
    published_only: bool = True,
    site_id: int | None = None,
) -> list[SiteSectionOut]:
    """Retrieve long-form narrative content blocks for a specific section or all sections."""
    resolved_site_id = (
        site_id
        if site_id is not None
        else resolve_site_id_by_slug(db, site_slug, published_only=published_only)
    )
    if resolved_site_id is None:
        return []

    sections = site_repo.get_site_sections(db, resolved_site_id, section_key)
    return [
        SiteSectionOut(
            content_id=s.content_id,
            site_id=s.site_id,
            section_key=s.section_key,
            title=s.title,
            body=s.body,
            display_order=s.display_order,
            language_code=s.language_code,
            source_status=s.source_status,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in sections
    ]


def get_site_pros_cons(
    db: Session,
    site_slug: str,
    *,
    published_only: bool = True,
    site_id: int | None = None,
) -> list[SiteProConOut]:
    """Retrieve structured advantages and limitations."""
    resolved_site_id = (
        site_id
        if site_id is not None
        else resolve_site_id_by_slug(db, site_slug, published_only=published_only)
    )
    if resolved_site_id is None:
        return []

    results = site_repo.get_site_pros_cons(db, resolved_site_id)
    items = []
    for point, source_title in results:
        items.append(
            SiteProConOut(
                point_id=point.point_id,
                site_id=point.site_id,
                point_type=point.point_type,
                title=point.title,
                body=point.body,
                evidence_note=point.evidence_note,
                source_id=point.source_id,
                source_title=source_title,
                display_order=point.display_order,
                confidence=float(point.confidence) if point.confidence is not None else None,
            )
        )
    return items


def get_site_metrics(
    db: Session,
    site_slug: str,
    *,
    published_only: bool = True,
    site_id: int | None = None,
) -> list[SiteMetricOut]:
    """Retrieve scientific measurements with units and uncertainties."""
    resolved_site_id = (
        site_id
        if site_id is not None
        else resolve_site_id_by_slug(db, site_slug, published_only=published_only)
    )
    if resolved_site_id is None:
        return []

    results = site_repo.get_site_metrics(db, resolved_site_id)
    items = []
    for metric, param, citation, source_title, source_url in results:
        items.append(
            SiteMetricOut(
                site_metric_id=metric.site_metric_id,
                site_id=metric.site_id,
                parameter_id=param.parameter_id,
                parameter_key=param.parameter_key,
                display_name=param.display_name,
                numeric_value=metric.numeric_value,
                text_value=metric.text_value,
                unit=metric.unit_override or param.unit,
                uncertainty_value=metric.uncertainty_value,
                methodology=metric.methodology,
                source_id=metric.source_id,
                source_title=source_title,
                source_citation=citation,
                source_url=source_url,
                data_quality_status=metric.data_quality_status or "unverified",
                dataset_version=metric.dataset_version,
                valid_from=metric.valid_from,
                valid_to=metric.valid_to,
                calculated_at=metric.calculated_at,
            )
        )
    return items


def get_site_media(
    db: Session,
    site_slug: str,
    *,
    published_only: bool = True,
    site_id: int | None = None,
) -> list[SiteMediaOut]:
    """Retrieve gallery assets for a landing site."""
    resolved_site_id = (
        site_id
        if site_id is not None
        else resolve_site_id_by_slug(db, site_slug, published_only=published_only)
    )
    if resolved_site_id is None:
        return []

    media_items = site_repo.get_site_media(db, resolved_site_id)
    return [
        SiteMediaOut(
            media_id=m.media_id,
            site_id=m.site_id,
            media_type=m.media_type,
            image_url=f"/storage/{m.file_path}",
            thumbnail_url=f"/storage/{m.thumbnail_path}" if m.thumbnail_path else None,
            original_filename=m.original_filename,
            mime_type=m.mime_type,
            file_size_bytes=m.file_size_bytes,
            width_px=m.width_px,
            height_px=m.height_px,
            caption=m.caption,
            credit=m.credit,
            alt_text=m.alt_text,
            source_id=m.source_id,
            sha256=m.sha256,
            display_order=m.display_order,
            is_primary=m.is_primary,
            created_at=m.created_at,
        )
        for m in media_items
    ]


def get_site_history(
    db: Session,
    site_slug: str,
    *,
    published_only: bool = True,
    site_id: int | None = None,
) -> list[SiteHistoryOut]:
    """Retrieve chronological discovery or mission history."""
    resolved_site_id = (
        site_id
        if site_id is not None
        else resolve_site_id_by_slug(db, site_slug, published_only=published_only)
    )
    if resolved_site_id is None:
        return []

    events = site_repo.get_site_history(db, resolved_site_id)
    return [
        SiteHistoryOut(
            history_id=h.history_id,
            site_id=h.site_id,
            event_date=h.event_date,
            title=h.title,
            description=h.description,
            source_id=h.source_id,
            display_order=h.display_order,
            created_at=h.created_at,
        )
        for h in events
    ]
