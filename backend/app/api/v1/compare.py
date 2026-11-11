"""API endpoints for two-site landing comparison and profile retrieval."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.rate_limit import compare_rate_limiter
from app.db.session import get_db
from app.schemas.comparison import (
    ComparisonProfileOut,
    ComparisonRequestIn,
    ComparisonResultOut,
)
from app.services import comparison_service

router = APIRouter(prefix="/compare", tags=["Comparison Engine"])


@router.get(
    "/profiles",
    response_model=list[ComparisonProfileOut],
    status_code=status.HTTP_200_OK,
    summary="List pre-configured comparison profiles",
    description="Retrieve all active mission comparison profiles with parameter weights and required rules.",
)
def list_profiles(db: Session = Depends(get_db)) -> list[ComparisonProfileOut]:
    """Retrieve all approved comparison profiles."""
    return comparison_service.get_comparison_profiles(db)


@router.post(
    "",
    response_model=ComparisonResultOut,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(compare_rate_limiter)],
    summary="Compare exactly two landing sites",
    description=(
        "Executes a deterministic scientific comparison between two selected landing sites "
        "evaluated against user mission purpose or an approved comparison profile."
    ),
)
def compare_sites(
    request: ComparisonRequestIn,
    db: Session = Depends(get_db),
) -> ComparisonResultOut:
    """Compare two landing sites and persist comparison run record."""
    return comparison_service.compare_two_sites(db, request)
