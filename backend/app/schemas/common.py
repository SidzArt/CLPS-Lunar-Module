"""Common Pydantic v2 schemas for API responses, errors, and health checks."""

from typing import Any

from pydantic import BaseModel, Field


class HealthStatus(BaseModel):
    """Health check status response."""

    status: str = Field(..., description="SYSTEM_OK, DEGRADED, or DOWN")
    version: str = Field(default="0.1.0")
    timestamp_utc: str
    environment: str


class ReadinessStatus(BaseModel):
    """Deep readiness check probing critical dependencies."""

    status: str
    database: bool
    database_latency_ms: float | None = None
    components: dict[str, Any] = Field(default_factory=dict)


class ErrorDetail(BaseModel):
    """Structured field-level validation error."""

    field: str
    message: str


class APIErrorResponse(BaseModel):
    """Standardized API error envelope."""

    code: str
    message: str
    field_errors: list[ErrorDetail] = Field(default_factory=list)
    request_id: str | None = None
