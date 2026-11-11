"""Pydantic v2 contracts for the Phase 7 Admin Portal, RBAC, Audit, Health, and Provenance."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class RoleOut(BaseModel):
    """Registered RBAC permission role definition."""

    role_id: int
    role_key: str
    description: str | None = None


class AdminUserOut(BaseModel):
    """Sanitized administrator account representation (never includes credential hashes)."""

    admin_id: UUID
    username: str
    display_name: str | None = None
    is_active: bool
    failed_login_count: int = 0
    locked_until: datetime | None = None
    password_updated_at: datetime | None = None
    password_must_rotate: bool = False
    created_at: datetime
    last_login_at: datetime | None = None
    roles: list[str] = Field(default_factory=list)
    active_sessions_count: int = 0


class AdminUserCreateIn(BaseModel):
    """Create a new administrator account with role assignments."""

    username: str = Field(..., min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9._-]+$")
    password: str = Field(..., min_length=12, max_length=128)
    display_name: str | None = Field(default=None, max_length=150)
    is_active: bool = True
    password_must_rotate: bool = False
    role_keys: list[str] = Field(..., min_length=1)


class AdminUserUpdateIn(BaseModel):
    """Update administrator profile, status, roles, or lockout state."""

    display_name: str | None = Field(default=None, max_length=150)
    is_active: bool | None = None
    role_keys: list[str] | None = Field(default=None, min_length=1)
    unlock_account: bool = False
    password_must_rotate: bool | None = None


class AdminResetPasswordIn(BaseModel):
    """Administrative credential reset payload enforcing password complexity."""

    new_password: str = Field(..., min_length=12, max_length=128)
    password_must_rotate: bool = True


class AdminSessionRevokeOut(BaseModel):
    """Result summary for admin session revocation."""

    admin_id: UUID
    revoked_sessions_count: int


class AdminOverviewOut(BaseModel):
    """Role-filtered summary dashboard overview without leaking restricted datasets."""

    username: str
    display_name: str | None = None
    roles: list[str]
    sites_total: int
    sites_published: int
    sites_draft: int
    sites_verified: int
    sites_archived: int
    media_total: int
    imports_total: int
    imports_open: int
    simulations_total: int
    codex_controllers_online: int | None = None
    codex_controllers_total: int | None = None
    codex_transport_mode: str | None = None
    active_firmware_versions_count: int | None = None
    recent_audit_count_24h: int | None = None
    degraded_components_count: int | None = None


class AuditLogEntryOut(BaseModel):
    """Structured audit trail row with sensitive snapshots redacted."""

    audit_id: int
    admin_id: UUID | None = None
    admin_username: str | None = None
    action_key: str
    entity_type: str
    entity_id: str | None = None
    before_snapshot: dict[str, Any] | None = None
    after_snapshot: dict[str, Any] | None = None
    ip_address: str | None = None
    occurred_at: datetime


class AuditLogPageOut(BaseModel):
    """Paginated audit log listing."""

    items: list[AuditLogEntryOut]
    total: int
    page: int
    page_size: int
    has_more: bool


class SystemComponentHealthOut(BaseModel):
    """Single subsystem live probe result persisted in health_checks."""

    component_key: str
    display_name: str
    component_type: str
    status: Literal["healthy", "degraded", "unavailable"]
    latency_ms: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    checked_at: datetime


class SystemHealthSummaryOut(BaseModel):
    """Aggregate admin system health snapshot (no host filesystem paths exposed)."""

    overall_status: Literal["healthy", "degraded", "unavailable"]
    checked_at: datetime
    components: list[SystemComponentHealthOut]


class DataSourceOut(BaseModel):
    """Scientific provenance source metadata."""

    source_id: int
    agency_name: str | None = None
    title: str
    publisher: str | None = None
    source_url: str | None = None
    publication_date: date | None = None
    accessed_at: datetime | None = None
    dataset_version: str | None = None
    licence: str | None = None
    citation_text: str | None = None
    checksum: str | None = None


class DataSourceCreateIn(BaseModel):
    """Create a scientific data source citation record."""

    title: str = Field(..., min_length=2, max_length=500)
    agency_name: str | None = Field(default=None, max_length=200)
    publisher: str | None = Field(default=None, max_length=200)
    source_url: str | None = Field(default=None, max_length=1000)
    publication_date: date | None = None
    dataset_version: str | None = Field(default=None, max_length=120)
    licence: str | None = Field(default=None, max_length=200)
    citation_text: str | None = None
    checksum: str | None = Field(default=None, max_length=128)


class DataSourceUpdateIn(BaseModel):
    """Partially update an authoritative data source citation."""

    title: str | None = Field(default=None, min_length=2, max_length=500)
    agency_name: str | None = Field(default=None, max_length=200)
    publisher: str | None = Field(default=None, max_length=200)
    source_url: str | None = Field(default=None, max_length=1000)
    publication_date: date | None = None
    dataset_version: str | None = Field(default=None, max_length=120)
    licence: str | None = Field(default=None, max_length=200)
    citation_text: str | None = None
    checksum: str | None = Field(default=None, max_length=128)


class ParameterDefinitionAdminOut(BaseModel):
    """Registered scientific parameter definition for site metric entry."""

    parameter_id: int
    parameter_key: str
    display_name: str
    description: str | None = None
    unit: str | None = None
    value_type: str
    comparison_direction: str
    target_value: float | None = None
    is_comparable: bool
    is_time_dependent: bool
    validation_min: float | None = None
    validation_max: float | None = None
    is_active: bool


class LunarRegionOut(BaseModel):
    """NASA exploration region metadata."""

    region_id: int
    region_code: str | None = None
    region_name: str
    description: str | None = None
    source_status: str


class SectionUpdateIn(BaseModel):
    """Update a landing site narrative content section."""

    section_key: str | None = Field(
        default=None,
        pattern="^(overview|history|geology|research|mission_relevance|limitations|other)$",
    )
    title: str | None = None
    body: str | None = Field(default=None, min_length=1)
    display_order: int | None = None
    language_code: str | None = Field(default=None, max_length=16)
    source_status: str | None = Field(default=None, max_length=50)


class ProConUpdateIn(BaseModel):
    """Update a structured advantage/limitation entry."""

    point_type: str | None = Field(default=None, pattern="^(PRO|CON)$")
    title: str | None = None
    body: str | None = Field(default=None, min_length=1)
    evidence_note: str | None = None
    source_id: int | None = None
    display_order: int | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class SiteHistoryCreateIn(BaseModel):
    """Create a chronological mission or discovery milestone."""

    event_date: date | None = None
    title: str = Field(..., min_length=1, max_length=300)
    description: str = Field(..., min_length=1)
    source_id: int | None = None
    display_order: int = 0


class SiteHistoryUpdateIn(BaseModel):
    """Update a chronological mission milestone."""

    event_date: date | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, min_length=1)
    source_id: int | None = None
    display_order: int | None = None


class SiteMetricUpsertItem(BaseModel):
    """Single scientific metric upsert with provenance enforcement for verified values."""

    parameter_id: int = Field(..., gt=0)
    numeric_value: float | None = None
    text_value: str | None = None
    unit_override: str | None = Field(default=None, max_length=50)
    uncertainty_value: float | None = None
    methodology: str | None = None
    source_id: int | None = Field(default=None, gt=0)
    data_quality_status: Literal["verified", "estimated", "unverified", "pending"] = "unverified"
    dataset_version: str | None = Field(default=None, max_length=100)

    @field_validator("source_id")
    @classmethod
    def check_verified_requires_source(cls, v: int | None, info: Any) -> int | None:
        return v


class SiteMetricsBulkUpsertIn(BaseModel):
    """Bulk update/upsert payload for landing-site metrics."""

    metrics: list[SiteMetricUpsertItem] = Field(..., min_length=1)


class MediaUpdateIn(BaseModel):
    """Update descriptive metadata, attribution, or ordering for a media asset."""

    caption: str | None = None
    credit: str | None = None
    alt_text: str | None = None
    display_order: int | None = None
    source_id: int | None = None
    media_type: Literal["image", "map", "chart", "other"] | None = None


class OrphanMediaFileOut(BaseModel):
    """Media file stored on disk that has no matching PostgreSQL site_media reference."""

    relative_path: str
    size_bytes: int


class AdminMediaListOut(BaseModel):
    """Paginated media catalogue listing paired with storage orphan diagnostics."""

    items: list[dict[str, Any]]
    total: int
    orphan_files: list[OrphanMediaFileOut] = Field(default_factory=list)


class ImportSummaryOut(BaseModel):
    """Summary entry for dataset import job list."""

    import_id: int
    filename: str
    source_id: int | None = None
    imported_by_admin_id: UUID | None = None
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    row_counts: dict[str, Any] | None = None
    error_report_path: str | None = None


class ImportListOut(BaseModel):
    """List of staged/committed/rolled-back dataset imports."""

    items: list[ImportSummaryOut]
    total: int
