"""Pydantic schemas for landing sites, sections, pros/cons, metrics, and media."""

from datetime import date, datetime
from typing import TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse[T](BaseModel):
    """Standard paginated container response."""

    items: list[T]
    total: int
    page: int
    page_size: int
    has_more: bool


class SiteCardOut(BaseModel):
    """Summary card representation for the site exploration list."""

    site_id: int
    site_slug: str
    site_code: str
    site_name: str
    region_id: int | None = None
    region_name: str | None = None
    latitude_deg: float
    longitude_deg: float
    elevation_m: float | None = None
    terrain_type: str | None = None
    overview_summary: str | None = None
    catalogue_status: str
    primary_thumbnail: str | None = None
    updated_at: datetime


class SiteDetailOut(BaseModel):
    """Full detail representation of a landing site profile."""

    site_id: int
    site_slug: str
    site_code: str
    site_name: str
    alternate_names: list[str] | None = None
    region_id: int | None = None
    region_name: str | None = None
    region_code: str | None = None
    latitude_deg: float
    longitude_deg: float
    elevation_m: float | None = None
    terrain_type: str | None = None
    overview_summary: str | None = None
    catalogue_status: str
    coordinate_reference: str
    seo_title: str | None = None
    seo_meta_description: str | None = None
    og_image_url: str | None = None
    primary_image_url: str | None = None
    available_sections: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class SiteSectionOut(BaseModel):
    """Long-form narrative section with uncapped content body."""

    content_id: int
    site_id: int
    section_key: str
    title: str | None = None
    body: str
    display_order: int
    language_code: str
    source_status: str
    created_at: datetime
    updated_at: datetime


class SiteProConOut(BaseModel):
    """Evidence-based advantage or limitation point."""

    point_id: int
    site_id: int
    point_type: str
    title: str | None = None
    body: str
    evidence_note: str | None = None
    source_id: int | None = None
    source_title: str | None = None
    display_order: int
    confidence: float | None = None


class SiteMetricOut(BaseModel):
    """Scientific observation or measurement with source and uncertainty."""

    site_metric_id: int
    site_id: int
    parameter_id: int
    parameter_key: str
    display_name: str
    numeric_value: float | None = None
    text_value: str | None = None
    unit: str | None = None
    uncertainty_value: float | None = None
    methodology: str | None = None
    source_id: int | None = None
    source_title: str | None = None
    source_citation: str | None = None
    source_url: str | None = None
    data_quality_status: str = "unverified"
    dataset_version: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    calculated_at: datetime | None = None


class SiteMediaOut(BaseModel):
    """Gallery media asset with attribution and dimensions."""

    media_id: int
    site_id: int
    media_type: str
    image_url: str
    thumbnail_url: str | None = None
    original_filename: str | None = None
    mime_type: str
    file_size_bytes: int
    width_px: int | None = None
    height_px: int | None = None
    caption: str | None = None
    credit: str | None = None
    alt_text: str
    source_id: int | None = None
    sha256: str
    display_order: int
    is_primary: bool
    created_at: datetime


class SiteHistoryOut(BaseModel):
    """Chronological mission or discovery milestone."""

    history_id: int
    site_id: int
    event_date: date | None = None
    title: str
    description: str
    source_id: int | None = None
    display_order: int
    created_at: datetime


class SiteCreateIn(BaseModel):
    """Admin input schema for creating a new landing site."""

    site_code: str = Field(..., min_length=2, max_length=100)
    site_name: str = Field(..., min_length=2, max_length=200)
    site_slug: str | None = Field(None, max_length=100)
    region_id: int | None = None
    alternate_names: list[str] | None = None
    latitude_deg: float = Field(..., ge=-90.0, le=90.0)
    longitude_deg: float = Field(..., ge=-180.0, le=180.0)
    elevation_m: float | None = None
    terrain_type: str | None = None
    overview_summary: str | None = None
    catalogue_status: str = Field(default="draft")
    coordinate_reference: str = Field(default="MOON_ME (IAU/NAIF Mean Earth/Polar Axis)")
    seo_title: str | None = None
    seo_meta_description: str | None = None


class SiteUpdateIn(BaseModel):
    """Admin input schema for updating an existing landing site."""

    site_name: str | None = None
    region_id: int | None = None
    alternate_names: list[str] | None = None
    latitude_deg: float | None = Field(None, ge=-90.0, le=90.0)
    longitude_deg: float | None = Field(None, ge=-180.0, le=180.0)
    elevation_m: float | None = None
    terrain_type: str | None = None
    overview_summary: str | None = None
    catalogue_status: str | None = None
    seo_title: str | None = None
    seo_meta_description: str | None = None


class SectionCreateIn(BaseModel):
    """Admin input schema for adding a narrative content block."""

    section_key: str = Field(
        ..., pattern="^(overview|history|geology|research|mission_relevance|limitations|other)$"
    )
    title: str | None = None
    body: str = Field(..., min_length=1)
    display_order: int = 0
    language_code: str = "en"
    source_status: str = "verified"


class ProConCreateIn(BaseModel):
    """Admin input schema for adding a pro or con point."""

    point_type: str = Field(..., pattern="^(PRO|CON)$")
    title: str | None = None
    body: str = Field(..., min_length=1)
    evidence_note: str | None = None
    source_id: int | None = None
    display_order: int = 0
    confidence: float | None = Field(None, ge=0.0, le=1.0)
