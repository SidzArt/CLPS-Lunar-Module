"""Admin endpoints for dataset import staging, validation, preview, commit, and rollback."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.audit import log_audit
from app.core.auth_dependency import RequireRole
from app.db.session import get_db
from app.models.admin import Admin
from app.repositories import import_repo
from app.schemas.admin_portal import ImportListOut, ImportSummaryOut
from app.schemas.imports import (
    ImportCommitOut,
    ImportDetailOut,
    ImportPreviewOut,
    ImportRollbackOut,
)
from app.services import import_service

router = APIRouter(prefix="/admin/imports", tags=["Admin Imports"])


@router.get(
    "",
    response_model=ImportListOut,
    summary="List staged, committed, and rolled-back dataset imports",
)
def list_dataset_imports(
    _admin: Annotated[Admin, Depends(RequireRole("research_admin", "site_editor", "system_admin"))],
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ImportListOut:
    """List dataset imports ordered newest first for provenance workbench management."""
    rows, total = import_repo.list_imports(db, status_filter=status_filter, limit=limit)
    return ImportListOut(
        items=[
            ImportSummaryOut(
                import_id=r.import_id,
                filename=r.filename,
                source_id=r.source_id,
                imported_by_admin_id=(
                    UUID(str(r.imported_by_admin_id)) if r.imported_by_admin_id else None
                ),
                status=r.status,
                started_at=r.started_at,
                completed_at=r.completed_at,
                row_counts=r.row_counts,
                error_report_path=r.error_report_path,
            )
            for r in rows
        ],
        total=total,
    )


@router.post(
    "",
    response_model=ImportPreviewOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and stage dataset file",
    description="Stages a CSV, XLSX, or GeoJSON dataset file and generates a non-destructive validation preview.",
)
async def upload_and_stage_dataset(
    file: UploadFile,
    source_id: Annotated[int | None, Form()] = None,
    admin: Admin = Depends(RequireRole("research_admin")),
    db: Session = Depends(get_db),
) -> ImportPreviewOut:
    """Stage dataset, validate coordinates, detect duplicates, and return preview report."""
    filename = file.filename or "unknown_dataset"
    file_bytes = await file.read()

    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded dataset file is empty.",
        )
    if len(file_bytes) > 15 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dataset file size exceeds maximum allowed limit of 15MB.",
        )

    try:
        dataset_import = import_service.stage_and_parse_dataset(
            db=db,
            file_bytes=file_bytes,
            filename=filename,
            admin_id=str(admin.admin_id),
            source_id=source_id,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    preview = import_service.validate_import_dataset(db, dataset_import.import_id)

    log_audit(
        db,
        action_key="IMPORT_STAGE",
        entity_type="dataset_imports",
        entity_id=str(dataset_import.import_id),
        admin_id=str(admin.admin_id),
        after_snapshot={
            "filename": filename,
            "total_rows": preview.total_rows,
            "valid": preview.valid_rows_count,
        },
    )
    db.commit()

    return preview


@router.get(
    "/{import_id}",
    response_model=ImportDetailOut,
    summary="Get import report",
    description="Retrieve status and metrics of a dataset import job.",
)
def get_import_report(
    import_id: int,
    admin: Annotated[Admin, Depends(RequireRole("research_admin"))],
    db: Annotated[Session, Depends(get_db)],
) -> ImportDetailOut:
    """Return import details."""
    dataset_import = import_repo.get_import(db, import_id)
    if not dataset_import:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset import {import_id} was not found.",
        )

    return ImportDetailOut(
        import_id=dataset_import.import_id,
        filename=dataset_import.filename,
        status=dataset_import.status,
        started_at=dataset_import.started_at,
        completed_at=dataset_import.completed_at,
        row_counts=dataset_import.row_counts,
        error_report_path=dataset_import.error_report_path,
    )


@router.get(
    "/{import_id}/preview",
    response_model=ImportPreviewOut,
    summary="Get import validation preview",
    description="Inspect validated rows, duplicate warnings, and invalid errors before commit.",
)
def get_import_preview(
    import_id: int,
    admin: Annotated[Admin, Depends(RequireRole("research_admin"))],
    db: Annotated[Session, Depends(get_db)],
) -> ImportPreviewOut:
    """Return validation preview report for staged import."""
    try:
        return import_service.validate_import_dataset(db, import_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/{import_id}/commit",
    response_model=ImportCommitOut,
    summary="Commit validated import",
    description="Transactionally commits all valid rows from staging into live landing_sites catalogue.",
)
def commit_staged_import(
    import_id: int,
    admin: Annotated[Admin, Depends(RequireRole("research_admin"))],
    db: Annotated[Session, Depends(get_db)],
) -> ImportCommitOut:
    """Execute transactional commit to production catalogue."""
    try:
        result = import_service.commit_import_dataset(db, import_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    log_audit(
        db,
        action_key="IMPORT_COMMIT",
        entity_type="dataset_imports",
        entity_id=str(import_id),
        admin_id=str(admin.admin_id),
        after_snapshot={"committed_sites": result.committed_sites_count},
    )
    db.commit()

    return result


@router.post(
    "/{import_id}/rollback",
    response_model=ImportRollbackOut,
    summary="Roll back import",
    description="Reverses committed import records or cancels uncommitted staging.",
)
def rollback_import(
    import_id: int,
    admin: Annotated[Admin, Depends(RequireRole("research_admin"))],
    db: Annotated[Session, Depends(get_db)],
) -> ImportRollbackOut:
    """Roll back committed sites or cancel uncommitted import."""
    try:
        result = import_service.rollback_import_dataset(db, import_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    log_audit(
        db,
        action_key="IMPORT_ROLLBACK",
        entity_type="dataset_imports",
        entity_id=str(import_id),
        admin_id=str(admin.admin_id),
        after_snapshot={"rolled_back_sites": result.rolled_back_sites_count},
    )
    db.commit()

    return result
