"""Pydantic schemas for AI-assisted landing site recommendation."""

from pydantic import BaseModel, Field


class AIAssistConstraint(BaseModel):
    """Hard filter constraint extracted from user prompt."""

    parameter_key: str
    operator: str = Field(..., description="lte, gte, lt, gt, eq")
    value: float


class AIAssistPriorityWeight(BaseModel):
    """Weight preference assigned to a parameter."""

    parameter_key: str
    weight: float = Field(..., ge=0.0, le=1.0)


class AIAssistExtractedRequirements(BaseModel):
    """Structured requirements extracted from natural-language mission description."""

    mission_summary: str
    required_parameters: list[str] = Field(default_factory=list)
    preferred_parameters: list[str] = Field(default_factory=list)
    constraints: list[AIAssistConstraint] = Field(default_factory=list)
    priority_weights: list[AIAssistPriorityWeight] = Field(default_factory=list)
    needs_clarification: bool = False


class AIAssistRequestIn(BaseModel):
    """Input payload for AI-assisted recommendation."""

    mission_request: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="Natural-language description of mission requirements and science goals",
        examples=[
            "Need a landing location suitable for long-duration surface research where solar illumination and direct Earth visibility are maximized, with lander slope under 15 degrees."
        ],
    )
    max_recommendations: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of candidate sites to recommend",
    )
    min_score_threshold: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Minimum overall weighted score required for recommendation",
    )


class SiteRecommendationOut(BaseModel):
    """A ranked candidate site recommended by the engine."""

    rank: int
    site_id: int
    site_code: str
    site_name: str
    site_slug: str
    latitude_deg: float
    longitude_deg: float
    elevation_m: float | None = None
    terrain_type: str | None = None
    overview_summary: str | None = None
    score: float
    rationale: str
    matched_parameters: dict[str, float | None] = Field(default_factory=dict)
    missing_parameters: list[str] = Field(default_factory=list)
    data_quality_status: str = "verified"


class AIAssistResponseOut(BaseModel):
    """Complete recommendation response with evidence-grounded candidate sites."""

    mission_request: str
    mission_summary: str
    extracted_requirements: AIAssistExtractedRequirements
    recommendations: list[SiteRecommendationOut]
    fallback_used: bool = False
    model_used: str
    execution_time_ms: float
    clarification_message: str | None = None
    limitations: list[str] = Field(default_factory=list)
