"""API endpoint for AI-assisted landing site recommendation."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.rate_limit import ai_assist_rate_limiter
from app.db.session import get_db
from app.schemas.ai_assist import AIAssistRequestIn, AIAssistResponseOut
from app.services import ai_assist_service

router = APIRouter(prefix="/ai-assist", tags=["AI Assist"])


@router.post(
    "/recommend",
    response_model=AIAssistResponseOut,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(ai_assist_rate_limiter)],
    summary="AI-assisted landing site recommendation",
    description=(
        "Translates a natural-language mission goal into structured parameters using local Ollama, "
        "filters and ranks candidate landing sites deterministically, and provides evidence-based rationale."
    ),
)
async def get_site_recommendations(
    request: AIAssistRequestIn,
    db: Session = Depends(get_db),
) -> AIAssistResponseOut:
    """Evaluate candidate sites against user mission requirements."""
    return await ai_assist_service.recommend_sites(db, request)
