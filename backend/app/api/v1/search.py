"""Public REST API endpoints for landing site search."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.search import SearchResultOut
from app.services import search_service

router = APIRouter(prefix="/search", tags=["Search"])


@router.get(
    "",
    response_model=list[SearchResultOut],
    summary="Search landing sites",
    description="Unified search covering site names, codes, and long-form research text.",
)
def search_landing_sites(
    q: str = Query(..., min_length=1, max_length=200, description="Search keyword"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results"),
    db: Session = Depends(get_db),
) -> list[SearchResultOut]:
    """Execute name and full-text content search."""
    return search_service.search_sites(db, q, limit)
