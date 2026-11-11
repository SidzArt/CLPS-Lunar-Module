"""Administrative diagnostic endpoints for SPICE kernels, DEM assets, and worker readiness."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.auth_dependency import RequireRole
from app.db.session import get_db
from app.models.admin import Admin
from app.schemas.simulation import AdminSimulationDiagnosticsOut
from app.services import simulation_service

router = APIRouter(prefix="/admin/simulations", tags=["Admin Simulations"])


@router.get(
    "/diagnostics",
    response_model=AdminSimulationDiagnosticsOut,
    status_code=status.HTTP_200_OK,
    summary="Inspect SPICE kernel coverage, LOLA DEM availability, horizon cache, and worker queue",
)
def get_simulation_asset_diagnostics(
    _admin: Annotated[
        Admin,
        Depends(
            RequireRole(
                "viewer",
                "research_admin",
                "site_editor",
                "hardware_operator",
                "hardware_admin",
                "system_admin",
            )
        ),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Authenticated admin diagnostic endpoint omitting host OS paths."""
    return simulation_service.get_admin_simulation_diagnostics(db)
