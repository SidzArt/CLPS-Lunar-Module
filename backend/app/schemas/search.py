"""Pydantic schemas for landing site search results."""

from pydantic import BaseModel


class SearchResultOut(BaseModel):
    """Unified search result entry."""

    site_id: int
    site_slug: str
    site_code: str
    site_name: str
    match_field: str  # 'name', 'alias', or 'content'
    match_snippet: str | None = None
    region_name: str | None = None
    latitude_deg: float
    longitude_deg: float
