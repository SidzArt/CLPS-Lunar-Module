"""Pydantic schemas for dataset import staging, preview, and commit."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ImportRowPreview(BaseModel):
    """Preview of a single staged record before commit."""

    row_id: int
    row_status: str  # 'valid' or 'invalid'
    site_code: str | None = None
    site_name: str | None = None
    latitude_deg: float | None = None
    longitude_deg: float | None = None
    action_type: str  # 'INSERT', 'UPDATE', or 'REJECT'
    validation_errors: dict[str, Any] | None = None


class ImportPreviewOut(BaseModel):
    """Preview summary returned before explicit commit."""

    import_id: int
    filename: str
    status: str
    total_rows: int
    valid_rows_count: int
    invalid_rows_count: int
    new_sites_count: int
    updated_sites_count: int
    rows: list[ImportRowPreview] = Field(default_factory=list)


class ImportCommitOut(BaseModel):
    """Result of an explicit transactional import commit."""

    import_id: int
    status: str
    committed_sites_count: int
    committed_rows_count: int
    execution_time_ms: float
    message: str


class ImportRollbackOut(BaseModel):
    """Result of an import rollback operation."""

    import_id: int
    status: str
    rolled_back_sites_count: int
    message: str


class ImportDetailOut(BaseModel):
    """Status and report of a dataset import."""

    import_id: int
    filename: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    row_counts: dict[str, Any] | None = None
    error_report_path: str | None = None
