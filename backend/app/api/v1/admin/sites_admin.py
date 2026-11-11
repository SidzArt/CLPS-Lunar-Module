"""Admin endpoints for landing site catalogue content management."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import log_audit
from app.core.auth_dependency import RequireRole
from app.db.session import get_db
from app.models.admin import Admin
from app.models.catalogue import LandingSite, NASARegion, SiteContent, SiteHistory, SiteProCon
from app.models.metrics import ParameterDefinition
from app.models.provenance import DataSource
from app.repositories import site_repo
from app.schemas.admin_portal import (
    LunarRegionOut,
    ProConUpdateIn,
    SectionUpdateIn,
    SiteHistoryCreateIn,
    SiteHistoryUpdateIn,
    SiteMetricsBulkUpsertIn,
)
from app.schemas.catalogue import (
    PaginatedResponse,
    ProConCreateIn,
    SectionCreateIn,
    SiteCardOut,
    SiteCreateIn,
    SiteDetailOut,
    SiteHistoryOut,
    SiteMediaOut,
    SiteMetricOut,
    SiteProConOut,
    SiteSectionOut,
    SiteUpdateIn,
)
from app.services import catalogue_service
from app.services.import_service import slugify

router = APIRouter(prefix="/admin", tags=["Admin Sites"])


def _get_site_or_404(db: Session, site_id: int) -> LandingSite:
    site = site_repo.get_site_by_id(db, site_id)
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Landing site with ID {site_id} was not found.",
        )
    return site


def _serialize_section(section: SiteContent) -> SiteSectionOut:
    return SiteSectionOut(
        content_id=section.content_id,
        site_id=section.site_id,
        section_key=section.section_key,
        title=section.title,
        body=section.body,
        display_order=section.display_order,
        language_code=section.language_code,
        source_status=section.source_status,
        created_at=section.created_at,
        updated_at=section.updated_at,
    )


def _serialize_pro_con(point: SiteProCon, source_title: str | None = None) -> SiteProConOut:
    return SiteProConOut(
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


def _serialize_history(entry: SiteHistory) -> SiteHistoryOut:
    return SiteHistoryOut(
        history_id=entry.history_id,
        site_id=entry.site_id,
        event_date=entry.event_date,
        title=entry.title,
        description=entry.description,
        source_id=entry.source_id,
        display_order=entry.display_order,
        created_at=entry.created_at,
    )


@router.get(
    "/regions",
    response_model=list[LunarRegionOut],
    summary="List NASA exploration regions",
)
def list_admin_regions(
    _admin: Annotated[
        Admin, Depends(RequireRole("site_editor", "research_admin", "system_admin", "viewer"))
    ],
    db: Annotated[Session, Depends(get_db)],
) -> list[LunarRegionOut]:
    """Return all NASA exploration regions for site metadata forms."""
    return [
        LunarRegionOut(
            region_id=r.region_id,
            region_code=r.region_code,
            region_name=r.region_name,
            description=r.description,
            source_status=r.source_status,
        )
        for r in site_repo.list_regions(db)
    ]


@router.get(
    "/sites",
    response_model=PaginatedResponse[SiteCardOut],
    summary="List all landing sites including drafts and archived entries",
)
def list_admin_sites(
    _admin: Annotated[
        Admin, Depends(RequireRole("site_editor", "research_admin", "system_admin", "viewer"))
    ],
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    region_id: Annotated[int | None, Query()] = None,
    catalogue_status: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    sort_by: Annotated[str, Query()] = "name",
) -> PaginatedResponse[SiteCardOut]:
    """Retrieve paginated landing sites across every workflow status for editors."""
    return catalogue_service.get_site_cards(
        db=db,
        page=page,
        page_size=page_size,
        region_id=region_id,
        catalogue_status=catalogue_status,
        search_query=search,
        sort_by=sort_by,
    )


@router.get(
    "/sites/{site_id}",
    response_model=SiteDetailOut,
    summary="Get full landing site dossier regardless of status",
)
def get_admin_site_detail(
    site_id: int,
    _admin: Annotated[
        Admin, Depends(RequireRole("site_editor", "research_admin", "system_admin", "viewer"))
    ],
    db: Annotated[Session, Depends(get_db)],
) -> SiteDetailOut:
    """Fetch complete site metadata including draft and archived dossiers."""
    site = _get_site_or_404(db, site_id)
    detail = catalogue_service.get_site_detail(db, site.site_slug, published_only=False)
    assert detail is not None
    return detail


@router.post(
    "/sites",
    response_model=SiteDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create landing site",
    description="Authorized endpoint for creating a new landing site record.",
)
def create_landing_site(
    payload: SiteCreateIn,
    admin: Annotated[Admin, Depends(RequireRole("site_editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> SiteDetailOut:
    """Create a new landing site record with slug generation."""
    if site_repo.get_site_by_code(db, payload.site_code):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Site with code '{payload.site_code}' already exists.",
        )

    site_slug = payload.site_slug or slugify(payload.site_code)
    if site_repo.get_site_by_slug(db, site_slug):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Site with slug '{site_slug}' already exists.",
        )

    if payload.region_id is not None and db.get(NASARegion, payload.region_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"NASA region ID {payload.region_id} was not found.",
        )

    site_dict = payload.model_dump()
    site_dict["site_slug"] = site_slug

    site = site_repo.create_site(db, site_dict)
    log_audit(
        db,
        action_key="SITE_CREATE",
        entity_type="landing_sites",
        entity_id=str(site.site_id),
        admin_id=str(admin.admin_id),
        after_snapshot={"site_code": site.site_code, "site_name": site.site_name},
    )
    db.commit()

    detail = catalogue_service.get_site_detail(db, site.site_slug, published_only=False)
    assert detail is not None
    return detail


@router.patch(
    "/sites/{site_id}",
    response_model=SiteDetailOut,
    summary="Update landing site",
    description="Authorized endpoint for editing an existing landing site.",
)
def update_landing_site(
    site_id: int,
    payload: SiteUpdateIn,
    admin: Annotated[Admin, Depends(RequireRole("site_editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> SiteDetailOut:
    """Update fields on an existing landing site."""
    site = _get_site_or_404(db, site_id)
    update_dict = payload.model_dump(exclude_unset=True)

    if (
        update_dict.get("region_id") is not None
        and db.get(NASARegion, update_dict["region_id"]) is None
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"NASA region ID {update_dict['region_id']} was not found.",
        )

    before_data = {"site_name": site.site_name, "catalogue_status": site.catalogue_status}
    site_repo.update_site(db, site, update_dict)
    log_audit(
        db,
        action_key="SITE_UPDATE",
        entity_type="landing_sites",
        entity_id=str(site.site_id),
        admin_id=str(admin.admin_id),
        before_snapshot=before_data,
        after_snapshot=update_dict,
    )
    db.commit()

    detail = catalogue_service.get_site_detail(db, site.site_slug, published_only=False)
    assert detail is not None
    return detail


@router.post(
    "/sites/{site_id}/archive",
    response_model=SiteDetailOut,
    summary="Archive a landing site safely instead of hard-deleting published data",
)
def archive_landing_site(
    site_id: int,
    admin: Annotated[Admin, Depends(RequireRole("site_editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> SiteDetailOut:
    """Transition a site to archived catalogue_status with before/after audit snapshots."""
    site = _get_site_or_404(db, site_id)
    before_status = site.catalogue_status
    site_repo.update_site(db, site, {"catalogue_status": "archived"})
    log_audit(
        db,
        action_key="SITE_ARCHIVE",
        entity_type="landing_sites",
        entity_id=str(site.site_id),
        admin_id=str(admin.admin_id),
        before_snapshot={"catalogue_status": before_status},
        after_snapshot={"catalogue_status": "archived"},
    )
    db.commit()
    detail = catalogue_service.get_site_detail(db, site.site_slug, published_only=False)
    assert detail is not None
    return detail


@router.delete(
    "/sites/{site_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a draft or archived landing site",
)
def delete_landing_site(
    site_id: int,
    admin: Annotated[Admin, Depends(RequireRole("site_editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Delete non-published site entries; published sites must be archived first."""
    site = _get_site_or_404(db, site_id)
    if site.catalogue_status == "published":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Published landing sites cannot be hard-deleted; archive the site first.",
        )
    before_snapshot = {
        "site_code": site.site_code,
        "site_slug": site.site_slug,
        "site_name": site.site_name,
        "catalogue_status": site.catalogue_status,
    }
    site_repo.delete_site(db, site)
    log_audit(
        db,
        action_key="SITE_DELETE",
        entity_type="landing_sites",
        entity_id=str(site_id),
        admin_id=str(admin.admin_id),
        before_snapshot=before_snapshot,
    )
    db.commit()
    return {"status": "DELETED", "site_id": site_id}


@router.get(
    "/sites/{site_id}/sections",
    response_model=list[SiteSectionOut],
    summary="List narrative sections for any status landing site",
)
def list_admin_site_sections(
    site_id: int,
    _admin: Annotated[
        Admin, Depends(RequireRole("site_editor", "research_admin", "system_admin", "viewer"))
    ],
    db: Annotated[Session, Depends(get_db)],
) -> list[SiteSectionOut]:
    _get_site_or_404(db, site_id)
    return [_serialize_section(s) for s in site_repo.get_site_sections(db, site_id)]


@router.post(
    "/sites/{site_id}/sections",
    response_model=SiteSectionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add narrative section",
    description="Add an uncapped long-form research content section to a landing site.",
)
def add_site_section(
    site_id: int,
    payload: SectionCreateIn,
    admin: Annotated[Admin, Depends(RequireRole("site_editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> SiteSectionOut:
    """Create a new narrative content section."""
    _get_site_or_404(db, site_id)

    section_dict = payload.model_dump()
    section_dict["site_id"] = site_id

    section = site_repo.create_section(db, section_dict)
    log_audit(
        db,
        action_key="SECTION_CREATE",
        entity_type="site_content",
        entity_id=str(section.content_id),
        admin_id=str(admin.admin_id),
        after_snapshot={"section_key": section.section_key, "title": section.title},
    )
    db.commit()

    return _serialize_section(section)


@router.patch(
    "/sites/{site_id}/sections/{content_id}",
    response_model=SiteSectionOut,
    summary="Update narrative content section",
)
def update_site_section(
    site_id: int,
    content_id: int,
    payload: SectionUpdateIn,
    admin: Annotated[Admin, Depends(RequireRole("site_editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> SiteSectionOut:
    _get_site_or_404(db, site_id)
    section = site_repo.get_section_by_id(db, content_id)
    if not section or section.site_id != site_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Section {content_id} was not found for site {site_id}.",
        )
    before = {"section_key": section.section_key, "title": section.title}
    update_dict = payload.model_dump(exclude_unset=True)
    site_repo.update_section(db, section, update_dict)
    log_audit(
        db,
        action_key="SECTION_UPDATE",
        entity_type="site_content",
        entity_id=str(section.content_id),
        admin_id=str(admin.admin_id),
        before_snapshot=before,
        after_snapshot=update_dict,
    )
    db.commit()
    db.refresh(section)
    return _serialize_section(section)


@router.delete(
    "/sites/{site_id}/sections/{content_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete narrative content section",
)
def delete_site_section(
    site_id: int,
    content_id: int,
    admin: Annotated[Admin, Depends(RequireRole("site_editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _get_site_or_404(db, site_id)
    section = site_repo.get_section_by_id(db, content_id)
    if not section or section.site_id != site_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Section {content_id} was not found for site {site_id}.",
        )
    before = {"section_key": section.section_key, "title": section.title}
    site_repo.delete_section(db, section)
    log_audit(
        db,
        action_key="SECTION_DELETE",
        entity_type="site_content",
        entity_id=str(content_id),
        admin_id=str(admin.admin_id),
        before_snapshot=before,
    )
    db.commit()
    return {"status": "DELETED", "content_id": content_id}


@router.get(
    "/sites/{site_id}/pros-cons",
    response_model=list[SiteProConOut],
    summary="List pros and cons for any status landing site",
)
def list_admin_site_pros_cons(
    site_id: int,
    _admin: Annotated[
        Admin, Depends(RequireRole("site_editor", "research_admin", "system_admin", "viewer"))
    ],
    db: Annotated[Session, Depends(get_db)],
) -> list[SiteProConOut]:
    _get_site_or_404(db, site_id)
    return [_serialize_pro_con(p, st) for p, st in site_repo.get_site_pros_cons(db, site_id)]


@router.post(
    "/sites/{site_id}/pros-cons",
    response_model=SiteProConOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add pro or con",
    description="Add a structured advantage or limitation point.",
)
def add_site_pro_con(
    site_id: int,
    payload: ProConCreateIn,
    admin: Annotated[Admin, Depends(RequireRole("site_editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> SiteProConOut:
    """Create a new pro or con evaluation point."""
    _get_site_or_404(db, site_id)

    source_title: str | None = None
    if payload.source_id is not None:
        src = db.get(DataSource, payload.source_id)
        if not src:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Data source ID {payload.source_id} was not found.",
            )
        source_title = src.title

    point_dict = payload.model_dump()
    point_dict["site_id"] = site_id

    point = site_repo.create_pro_con(db, point_dict)
    log_audit(
        db,
        action_key="PROCON_CREATE",
        entity_type="site_pros_cons",
        entity_id=str(point.point_id),
        admin_id=str(admin.admin_id),
        after_snapshot={"point_type": point.point_type, "title": point.title},
    )
    db.commit()

    return _serialize_pro_con(point, source_title)


@router.patch(
    "/sites/{site_id}/pros-cons/{point_id}",
    response_model=SiteProConOut,
    summary="Update pro or con entry",
)
def update_site_pro_con(
    site_id: int,
    point_id: int,
    payload: ProConUpdateIn,
    admin: Annotated[Admin, Depends(RequireRole("site_editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> SiteProConOut:
    _get_site_or_404(db, site_id)
    point = site_repo.get_pro_con_by_id(db, point_id)
    if not point or point.site_id != site_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pro/Con entry {point_id} was not found for site {site_id}.",
        )
    update_dict = payload.model_dump(exclude_unset=True)
    if (
        update_dict.get("source_id") is not None
        and db.get(DataSource, update_dict["source_id"]) is None
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Data source ID {update_dict['source_id']} was not found.",
        )
    before = {"point_type": point.point_type, "title": point.title}
    site_repo.update_pro_con(db, point, update_dict)
    log_audit(
        db,
        action_key="PROCON_UPDATE",
        entity_type="site_pros_cons",
        entity_id=str(point.point_id),
        admin_id=str(admin.admin_id),
        before_snapshot=before,
        after_snapshot=update_dict,
    )
    db.commit()
    db.refresh(point)
    src = db.get(DataSource, point.source_id) if point.source_id else None
    return _serialize_pro_con(point, src.title if src else None)


@router.delete(
    "/sites/{site_id}/pros-cons/{point_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete pro or con entry",
)
def delete_site_pro_con(
    site_id: int,
    point_id: int,
    admin: Annotated[Admin, Depends(RequireRole("site_editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _get_site_or_404(db, site_id)
    point = site_repo.get_pro_con_by_id(db, point_id)
    if not point or point.site_id != site_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pro/Con entry {point_id} was not found for site {site_id}.",
        )
    before = {"point_type": point.point_type, "title": point.title}
    site_repo.delete_pro_con(db, point)
    log_audit(
        db,
        action_key="PROCON_DELETE",
        entity_type="site_pros_cons",
        entity_id=str(point_id),
        admin_id=str(admin.admin_id),
        before_snapshot=before,
    )
    db.commit()
    return {"status": "DELETED", "point_id": point_id}


@router.get(
    "/sites/{site_id}/history",
    response_model=list[SiteHistoryOut],
    summary="List chronological mission history for any status landing site",
)
def list_admin_site_history(
    site_id: int,
    _admin: Annotated[
        Admin, Depends(RequireRole("site_editor", "research_admin", "system_admin", "viewer"))
    ],
    db: Annotated[Session, Depends(get_db)],
) -> list[SiteHistoryOut]:
    _get_site_or_404(db, site_id)
    return [_serialize_history(h) for h in site_repo.get_site_history(db, site_id)]


@router.post(
    "/sites/{site_id}/history",
    response_model=SiteHistoryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add chronological mission or discovery history milestone",
)
def add_site_history(
    site_id: int,
    payload: SiteHistoryCreateIn,
    admin: Annotated[Admin, Depends(RequireRole("site_editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> SiteHistoryOut:
    _get_site_or_404(db, site_id)
    if payload.source_id is not None and db.get(DataSource, payload.source_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Data source ID {payload.source_id} was not found.",
        )
    data = payload.model_dump()
    data["site_id"] = site_id
    entry = site_repo.create_history(db, data)
    log_audit(
        db,
        action_key="HISTORY_CREATE",
        entity_type="site_history",
        entity_id=str(entry.history_id),
        admin_id=str(admin.admin_id),
        after_snapshot={"site_id": site_id, "title": entry.title},
    )
    db.commit()
    return _serialize_history(entry)


@router.patch(
    "/sites/{site_id}/history/{history_id}",
    response_model=SiteHistoryOut,
    summary="Update mission history milestone",
)
def update_site_history(
    site_id: int,
    history_id: int,
    payload: SiteHistoryUpdateIn,
    admin: Annotated[Admin, Depends(RequireRole("site_editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> SiteHistoryOut:
    _get_site_or_404(db, site_id)
    entry = site_repo.get_history_by_id(db, history_id)
    if not entry or entry.site_id != site_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"History entry {history_id} was not found for site {site_id}.",
        )
    update_dict = payload.model_dump(exclude_unset=True)
    if (
        update_dict.get("source_id") is not None
        and db.get(DataSource, update_dict["source_id"]) is None
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Data source ID {update_dict['source_id']} was not found.",
        )
    before = {"title": entry.title}
    site_repo.update_history(db, entry, update_dict)
    log_audit(
        db,
        action_key="HISTORY_UPDATE",
        entity_type="site_history",
        entity_id=str(history_id),
        admin_id=str(admin.admin_id),
        before_snapshot=before,
        after_snapshot=update_dict,
    )
    db.commit()
    db.refresh(entry)
    return _serialize_history(entry)


@router.delete(
    "/sites/{site_id}/history/{history_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete mission history milestone",
)
def delete_site_history(
    site_id: int,
    history_id: int,
    admin: Annotated[Admin, Depends(RequireRole("site_editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _get_site_or_404(db, site_id)
    entry = site_repo.get_history_by_id(db, history_id)
    if not entry or entry.site_id != site_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"History entry {history_id} was not found for site {site_id}.",
        )
    before = {"title": entry.title}
    site_repo.delete_history(db, entry)
    log_audit(
        db,
        action_key="HISTORY_DELETE",
        entity_type="site_history",
        entity_id=str(history_id),
        admin_id=str(admin.admin_id),
        before_snapshot=before,
    )
    db.commit()
    return {"status": "DELETED", "history_id": history_id}


@router.get(
    "/sites/{site_id}/metrics",
    response_model=list[SiteMetricOut],
    summary="List scientific metrics for any status landing site",
)
def list_admin_site_metrics(
    site_id: int,
    _admin: Annotated[
        Admin, Depends(RequireRole("site_editor", "research_admin", "system_admin", "viewer"))
    ],
    db: Annotated[Session, Depends(get_db)],
) -> list[SiteMetricOut]:
    site = _get_site_or_404(db, site_id)
    return catalogue_service.get_site_metrics(db, site.site_slug, published_only=False)


@router.get(
    "/sites/{site_id}/media",
    response_model=list[SiteMediaOut],
    summary="List gallery media assets for any status landing site",
)
def list_admin_site_media(
    site_id: int,
    _admin: Annotated[
        Admin, Depends(RequireRole("site_editor", "research_admin", "system_admin", "viewer"))
    ],
    db: Annotated[Session, Depends(get_db)],
) -> list[SiteMediaOut]:
    site = _get_site_or_404(db, site_id)
    return catalogue_service.get_site_media(db, site.site_slug, published_only=False)


@router.put(
    "/sites/{site_id}/metrics",
    response_model=list[SiteMetricOut],
    summary="Bulk upsert verified or estimated scientific metrics for a landing site",
)
def upsert_site_metrics_bulk(
    site_id: int,
    payload: SiteMetricsBulkUpsertIn,
    admin: Annotated[Admin, Depends(RequireRole("site_editor", "research_admin"))],
    db: Annotated[Session, Depends(get_db)],
) -> list[SiteMetricOut]:
    """Validate bounds & provenance, then atomically upsert site metrics with audit logging."""
    site = _get_site_or_404(db, site_id)
    param_ids = {item.parameter_id for item in payload.metrics}
    params = {
        p.parameter_id: p
        for p in db.scalars(
            select(ParameterDefinition).where(ParameterDefinition.parameter_id.in_(param_ids))
        ).all()
    }
    changed_keys: list[str] = []

    for item in payload.metrics:
        param = params.get(item.parameter_id)
        if not param:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Parameter definition {item.parameter_id} was not found.",
            )
        if item.data_quality_status == "verified" and item.source_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"Metric '{param.parameter_key}' cannot be marked 'verified' without an "
                    "explicit source_id provenance citation."
                ),
            )
        if item.source_id is not None and db.get(DataSource, item.source_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Data source ID {item.source_id} was not found.",
            )
        if item.numeric_value is not None:
            if param.validation_min is not None and item.numeric_value < param.validation_min:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Value {item.numeric_value} for '{param.parameter_key}' is below "
                        f"minimum bound {param.validation_min}."
                    ),
                )
            if param.validation_max is not None and item.numeric_value > param.validation_max:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Value {item.numeric_value} for '{param.parameter_key}' exceeds "
                        f"maximum bound {param.validation_max}."
                    ),
                )

        metric_data = item.model_dump(exclude={"parameter_id"})
        site_repo.upsert_site_metric(
            db,
            site_id=site.site_id,
            parameter_id=item.parameter_id,
            metric_data=metric_data,
        )
        changed_keys.append(param.parameter_key)

    log_audit(
        db,
        action_key="SITE_METRICS_UPSERT",
        entity_type="site_metrics",
        entity_id=str(site.site_id),
        admin_id=str(admin.admin_id),
        after_snapshot={"updated_parameters": changed_keys},
    )
    db.commit()
    return catalogue_service.get_site_metrics(db, site.site_slug, published_only=False)
