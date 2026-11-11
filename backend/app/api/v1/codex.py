"""Public and operator REST API routes for CODEX hardware status, prepare, execute, and E-STOP."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.auth_dependency import RequireRole
from app.core.rate_limit import codex_rate_limiter
from app.db.session import get_db
from app.models.admin import Admin
from app.schemas.codex import (
    CodexEstopIn,
    CodexEstopOut,
    CodexRunEventsOut,
    CodexRunExecuteIn,
    CodexRunPrepareIn,
    CodexRunPrepareOut,
    CodexRunStatusOut,
    PublicCodexStatusOut,
)
from app.services import codex_service

router = APIRouter(prefix="/codex", tags=["CODEX Hardware"])

OperatorOrAdmin = Annotated[
    Admin,
    Depends(RequireRole("hardware_operator", "hardware_admin", "system_admin")),
]


@router.get(
    "/status",
    response_model=PublicCodexStatusOut,
    status_code=status.HTTP_200_OK,
    summary="Get sanitized CODEX controller readiness summary",
)
def get_codex_public_status(db: Annotated[Session, Depends(get_db)]) -> dict:
    """Expose non-sensitive readiness flags for public mission UI status pills."""
    return codex_service.get_public_status_payload(db)


@router.post(
    "/runs/prepare",
    response_model=CodexRunPrepareOut,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(codex_rate_limiter)],
    summary="Prepare CODEX motion/LED plan and 16-step pre-flight without actuating hardware",
)
def prepare_codex_run(
    payload: CodexRunPrepareIn,
    operator: OperatorOrAdmin,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Compute kinematics, Moon LED region resolution, and 16-step pre-flight safely."""
    return codex_service.prepare_codex_run(
        db,
        payload=payload.model_dump(),
        operator_admin_id=operator.admin_id,
    )


@router.post(
    "/runs",
    response_model=CodexRunStatusOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(codex_rate_limiter)],
    summary="Execute confirmed CODEX hardware run with strict 16-step pre-flight gating",
)
def execute_codex_run(
    payload: CodexRunExecuteIn,
    operator: OperatorOrAdmin,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Dispatch signed Protocol v1 commands only after confirmation and verification pass."""
    return codex_service.execute_codex_run(
        db,
        payload=payload.model_dump(),
        operator_admin_id=operator.admin_id,
    )


@router.get(
    "/runs/{run_id}",
    response_model=CodexRunStatusOut,
    status_code=status.HTTP_200_OK,
    summary="Get CODEX hardware run state and per-controller acknowledgements",
)
def get_codex_run(
    run_id: UUID,
    operator: OperatorOrAdmin,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Return execution state, command metadata, and per-device acks."""
    return codex_service.get_hardware_run_status(db, run_id)


@router.get(
    "/runs/{run_id}/events",
    response_model=CodexRunEventsOut,
    status_code=status.HTTP_200_OK,
    summary="List chronological telemetry and fault events for a CODEX run",
)
def get_codex_run_events(
    run_id: UUID,
    operator: OperatorOrAdmin,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Return chronological lifecycle and controller events for a CODEX run."""
    return codex_service.get_hardware_run_events(db, run_id)


@router.post(
    "/estop",
    response_model=CodexEstopOut,
    status_code=status.HTTP_200_OK,
    summary="Trigger immediate highest-priority CODEX hardware emergency stop",
)
def trigger_codex_estop(
    payload: CodexEstopIn,
    operator: OperatorOrAdmin,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Immediately dispatch E-STOP across controllers, abort active runs, and latch fault."""
    return codex_service.trigger_codex_estop(
        db,
        reason=payload.reason,
        hardware_run_id=payload.hardware_run_id,
        operator_admin_id=operator.admin_id,
    )
