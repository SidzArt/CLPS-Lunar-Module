"""Public REST API endpoints for landing site exploration and dossier sections."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
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
from app.services import catalogue_service

router = APIRouter(prefix="/sites", tags=["Landing Sites"])


@router.get(
    "",
    response_model=PaginatedResponse[SiteCardOut],
    summary="List landing sites",
    description="Retrieve paginated site cards with coordinates and primary thumbnails.",
)
def list_landing_sites(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    region_id: int | None = Query(None, description="Filter by NASA region ID"),
    status_filter: str = Query(
        "published",
        alias="status",
        description="Public catalogue filter (only 'published' is publicly exposed)",
    ),
    search: str | None = Query(None, description="Search term for site name or code"),
    sort: str = Query(
        "name", description="Sort order: name, elevation_asc, elevation_desc, updated_at"
    ),
    db: Session = Depends(get_db),
) -> PaginatedResponse[SiteCardOut]:
    """Return paginated published landing site cards."""
    if status_filter != "published":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Public landing-site catalogue only exposes sites with status='published'.",
        )
    return catalogue_service.get_site_cards(
        db=db,
        page=page,
        page_size=page_size,
        region_id=region_id,
        catalogue_status="published",
        search_query=search,
        sort_by=sort,
    )


@router.get(
    "/{site_slug}",
    response_model=SiteDetailOut,
    summary="Get landing site dossier",
    description="Retrieve comprehensive site profile by unique permanent slug.",
)
def get_site_by_slug(
    site_slug: str,
    db: Session = Depends(get_db),
) -> SiteDetailOut:
    """Return full landing site profile."""
    site = catalogue_service.get_site_detail(db, site_slug)
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Landing site with slug '{site_slug}' was not found.",
        )
    return site


def _require_published_site_id(db: Session, site_slug: str) -> int:
    """Resolve published site_id by slug/id or raise HTTP 404 without eager relation loads."""
    site_id = catalogue_service.resolve_site_id_by_slug(db, site_slug)
    if site_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Landing site with slug '{site_slug}' was not found.",
        )
    return site_id


@router.get(
    "/{site_slug}/sections",
    response_model=list[SiteSectionOut],
    summary="Get all site narrative sections",
    description="Retrieve all narrative content sections for a site.",
)
def get_site_sections(
    site_slug: str,
    section_key: str | None = Query(None, description="Optional filter by section key"),
    db: Session = Depends(get_db),
) -> list[SiteSectionOut]:
    """Return all narrative content sections for a site."""
    site_id = _require_published_site_id(db, site_slug)
    return catalogue_service.get_site_sections(db, site_slug, section_key, site_id=site_id)


@router.get(
    "/{site_slug}/sections/{section_key}",
    response_model=list[SiteSectionOut],
    summary="Get site narrative section",
    description="Retrieve uncapped long-form research text for a specific section.",
)
def get_site_section(
    site_slug: str,
    section_key: str,
    db: Session = Depends(get_db),
) -> list[SiteSectionOut]:
    """Return narrative content sections (overview, history, geology, research, etc.)."""
    site_id = _require_published_site_id(db, site_slug)
    return catalogue_service.get_site_sections(db, site_slug, section_key, site_id=site_id)


@router.get(
    "/{site_slug}/pros-cons",
    response_model=list[SiteProConOut],
    summary="Get site pros and cons",
    description="Retrieve structured evidence-based advantages and limitations.",
)
def get_site_pros_cons(
    site_slug: str,
    db: Session = Depends(get_db),
) -> list[SiteProConOut]:
    """Return site pros and cons."""
    site_id = _require_published_site_id(db, site_slug)
    return catalogue_service.get_site_pros_cons(db, site_slug, site_id=site_id)


@router.get(
    "/{site_slug}/metrics",
    response_model=list[SiteMetricOut],
    summary="Get scientific statistics",
    description="Retrieve measurements with units, sources, methodologies, and uncertainties.",
)
def get_site_metrics(
    site_slug: str,
    db: Session = Depends(get_db),
) -> list[SiteMetricOut]:
    """Return scientific metrics for site."""
    site_id = _require_published_site_id(db, site_slug)
    return catalogue_service.get_site_metrics(db, site_slug, site_id=site_id)


@router.get(
    "/{site_slug}/media",
    response_model=list[SiteMediaOut],
    summary="Get site media gallery",
    description="Retrieve gallery images with dimensions, thumbnails, alt text, and credits.",
)
def get_site_media(
    site_slug: str,
    db: Session = Depends(get_db),
) -> list[SiteMediaOut]:
    """Return gallery media assets."""
    site_id = _require_published_site_id(db, site_slug)
    return catalogue_service.get_site_media(db, site_slug, site_id=site_id)


@router.get(
    "/{site_slug}/history",
    response_model=list[SiteHistoryOut],
    summary="Get site history milestones",
    description="Retrieve chronological mission and research milestones.",
)
def get_site_history(
    site_slug: str,
    db: Session = Depends(get_db),
) -> list[SiteHistoryOut]:
    """Return chronological history events."""
    site_id = _require_published_site_id(db, site_slug)
    return catalogue_service.get_site_history(db, site_slug, site_id=site_id)
