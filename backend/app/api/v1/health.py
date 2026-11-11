"""Health and readiness diagnostic endpoints."""

import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.common import HealthStatus, ReadinessStatus

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthStatus,
    summary="Basic liveness check",
    description="Returns immediate 200 OK if FastAPI process is responsive.",
)
def liveness_check() -> HealthStatus:
    """Check if the backend process is alive."""
    return HealthStatus(
        status="SYSTEM_OK",
        version="0.1.0",
        timestamp_utc=datetime.now(UTC).isoformat(),
        environment=settings.APP_ENV,
    )


@router.get(
    "/ready",
    response_model=ReadinessStatus,
    summary="Readiness check probing PostgreSQL",
    description="Tests active database query execution and returns latency.",
)
def readiness_check(db: Annotated[Session, Depends(get_db)]):
    """Test active database connectivity and component availability."""
    db_ok = False
    db_latency: float | None = None

    start_time = time.perf_counter()
    try:
        # Run a fast ping query to verify connection
        db.execute(text("SELECT 1;"))
        db_latency = (time.perf_counter() - start_time) * 1000.0
        db_ok = True
    except (SQLAlchemyError, OSError):
        db_ok = False

    overall_status = "READY" if db_ok else "NOT_READY"
    status_code = status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE

    response_data = ReadinessStatus(
        status=overall_status,
        database=db_ok,
        database_latency_ms=round(db_latency, 2) if db_latency is not None else None,
        components={
            "database_engine": "PostgreSQL 18 + psycopg 3",
            "environment": settings.APP_ENV,
            "debug": settings.DEBUG,
        },
    )

    return JSONResponse(status_code=status_code, content=response_data.model_dump())
