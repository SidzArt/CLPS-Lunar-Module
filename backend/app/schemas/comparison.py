"""Pydantic schemas for landing site comparison engine."""

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class ComparisonCustomParameterIn(BaseModel):
    """Custom weight and target override for a specific parameter."""

    parameter_key: str = Field(..., min_length=1, max_length=100)
    weight: float = Field(..., ge=0.0, le=1.0, description="Relative priority weight [0, 1]")
    required: bool = Field(default=False, description="Whether missing data blocks overall scoring")
    target_value: float | None = Field(
        default=None, description="Optional target value for target-direction metrics"
    )


class ComparisonRequestIn(BaseModel):
    """Input payload to compare exactly two landing sites."""

    site_a_id: int = Field(..., gt=0, description="Primary landing site ID")
    site_b_id: int = Field(..., gt=0, description="Comparison landing site ID")
    mission_purpose: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="Scientific or operational purpose of the comparison",
        examples=["Evaluate sites for high continuous solar power and safe lander slopes."],
    )
    profile_key: str | None = Field(
        default=None,
        description="Optional pre-configured comparison profile key (e.g. solar_maximization)",
    )
    profile_id: int | None = Field(
        default=None,
        description="Optional pre-configured comparison profile ID",
    )
    custom_parameters: list[ComparisonCustomParameterIn] | None = Field(
        default=None,
        description="Optional custom parameter weights and requirements overriding profile",
    )

    @model_validator(mode="after")
    def validate_request(self) -> "ComparisonRequestIn":
        """Enforce that exactly two distinct sites are supplied and custom weights sum to 1.0."""
        if self.site_a_id == self.site_b_id:
            raise ValueError(
                "Cannot compare a site to itself. Exactly two distinct site IDs must be provided."
            )
        if self.custom_parameters is not None and len(self.custom_parameters) > 0:
            total_weight = sum(cp.weight for cp in self.custom_parameters)
            if abs(total_weight - 1.0) > 0.01:
                raise ValueError(
                    f"Custom parameter weights must sum to 1.0 within tolerance (±0.01). Current sum: {total_weight:.4f}."
                )
        return self


class ParameterComparisonOut(BaseModel):
    """Detailed parameter-by-parameter evaluation row."""

    parameter_key: str
    display_name: str
    description: str | None = None
    unit: str | None = None
    value_type: str
    comparison_direction: str  # higher, lower, target, context, informational
    value_a: float | None = None
    value_b: float | None = None
    text_value_a: str | None = None
    text_value_b: str | None = None
    absolute_difference: float | None = None
    relative_difference_percent: float | None = None
    normalised_a: float | None = None
    normalised_b: float | None = None
    winner_key: str  # site_a, site_b, tie, both, none
    weight: float | None = None
    required: bool = False
    is_scoreable: bool = True
    benchmark_min: float | None = None
    benchmark_max: float | None = None
    data_quality_status: str = "verified"
    source_reference: str | None = None
    dataset_version_a: str | None = None
    dataset_version_b: str | None = None
    observation_time_a: datetime | None = None
    observation_time_b: datetime | None = None
    compatibility_note: str | None = None
    explanation: str


class ComparisonProfileParameterOut(BaseModel):
    """Parameter rule within a comparison profile."""

    parameter_key: str
    display_name: str
    unit: str | None = None
    weight: float
    required: bool
    target_value: float | None = None
    comparison_direction: str


class ComparisonProfileOut(BaseModel):
    """Pre-configured comparison mission profile."""

    profile_id: int
    profile_key: str
    name: str
    purpose_description: str | None = None
    version: str
    parameters: list[ComparisonProfileParameterOut] = Field(default_factory=list)


class ComparisonResultOut(BaseModel):
    """Complete response payload for a two-site comparison query."""

    run_id: str
    site_a_id: int
    site_b_id: int
    site_a_name: str
    site_b_name: str
    site_a_code: str
    site_b_code: str
    site_a_slug: str
    site_b_slug: str
    mission_purpose: str
    profile_key: str | None = None
    profile_name: str | None = None
    algorithm_version: str = "v1.0"
    data_coverage: str  # complete, partial, insufficient_data
    overall_score_a: float | None = None
    overall_score_b: float | None = None
    overall_winner: str  # site_a, site_b, tie, undetermined
    winner_site_name: str | None = None
    parameters: list[ParameterComparisonOut]
    scientific_conclusion: str
    limitations_and_caveats: list[str]
    created_at: datetime
