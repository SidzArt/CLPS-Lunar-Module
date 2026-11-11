"""SQLAlchemy models for the lunar landing site catalogue and narrative blocks."""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class NASARegion(Base):
    """Broad lunar geographical or mission region containing candidate points."""

    __tablename__ = "nasa_regions"

    region_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    region_code: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    region_name: Mapped[str] = mapped_column(Text, nullable=False)
    mission_context: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    boundary_geojson: Mapped[dict | None] = mapped_column(JSONB)
    source_id: Mapped[int | None] = mapped_column(BigInteger)
    source_status: Mapped[str] = mapped_column(String(50), default="official")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    sites: Mapped[list["LandingSite"]] = relationship("LandingSite", back_populates="region")

    __table_args__ = (
        CheckConstraint(
            "source_status IN ('official', 'research', 'project-curated')",
            name="check_region_source_status",
        ),
    )


class LandingSite(Base):
    """Specific candidate lunar landing location or science target."""

    __tablename__ = "landing_sites"

    site_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    region_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("nasa_regions.region_id", ondelete="RESTRICT"), index=True
    )
    site_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    site_slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    site_name: Mapped[str] = mapped_column(Text, nullable=False)
    alternate_names: Mapped[list | None] = mapped_column(ARRAY(Text))

    latitude_deg: Mapped[float] = mapped_column(Numeric(10, 7), nullable=False)
    longitude_deg: Mapped[float] = mapped_column(Numeric(10, 7), nullable=False)
    elevation_m: Mapped[float | None] = mapped_column(Float)
    terrain_type: Mapped[str | None] = mapped_column(Text)
    overview_summary: Mapped[str | None] = mapped_column(Text)
    catalogue_status: Mapped[str] = mapped_column(String(50), default="draft", index=True)
    coordinate_reference: Mapped[str] = mapped_column(
        Text, default="MOON_ME (IAU/NAIF Mean Earth/Polar Axis)"
    )

    # SEO metadata
    seo_title: Mapped[str | None] = mapped_column(String(150))
    seo_meta_description: Mapped[str | None] = mapped_column(String(300))
    og_image_url: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    region: Mapped[Optional["NASARegion"]] = relationship("NASARegion", back_populates="sites")
    aliases: Mapped[list["SiteAlias"]] = relationship(
        "SiteAlias", back_populates="site", cascade="all, delete-orphan"
    )
    content_sections: Mapped[list["SiteContent"]] = relationship(
        "SiteContent", back_populates="site", cascade="all, delete-orphan"
    )
    pros_cons: Mapped[list["SiteProCon"]] = relationship(
        "SiteProCon", back_populates="site", cascade="all, delete-orphan"
    )
    media: Mapped[list["SiteMedia"]] = relationship(
        "SiteMedia", back_populates="site", cascade="all, delete-orphan"
    )
    history_events: Mapped[list["SiteHistory"]] = relationship(
        "SiteHistory", back_populates="site", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "latitude_deg >= -90.0 AND latitude_deg <= 90.0",
            name="check_site_latitude_range",
        ),
        CheckConstraint(
            "longitude_deg >= -180.0 AND longitude_deg <= 180.0",
            name="check_site_longitude_range",
        ),
        CheckConstraint(
            "catalogue_status IN ('draft', 'verified', 'published', 'archived')",
            name="check_site_catalogue_status",
        ),
        Index("idx_landing_sites_region_status", "region_id", "catalogue_status"),
        Index("idx_landing_sites_coords", "latitude_deg", "longitude_deg"),
    )


class SiteAlias(Base):
    """Alternative naming and designations for a landing site."""

    __tablename__ = "site_aliases"

    alias_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("landing_sites.site_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    alias_text: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    language_code: Mapped[str] = mapped_column(String(16), default="en")
    source_id: Mapped[int | None] = mapped_column(BigInteger)

    site: Mapped["LandingSite"] = relationship("LandingSite", back_populates="aliases")


class SiteContent(Base):
    """Repeatable long-form narrative content blocks with uncapped PostgreSQL TEXT."""

    __tablename__ = "site_content"

    content_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("landing_sites.site_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    language_code: Mapped[str] = mapped_column(String(16), default="en")
    source_status: Mapped[str] = mapped_column(String(50), default="verified")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    site: Mapped["LandingSite"] = relationship("LandingSite", back_populates="content_sections")

    __table_args__ = (
        CheckConstraint(
            "section_key IN ('overview', 'history', 'geology', 'research', 'mission_relevance', 'limitations', 'other')",
            name="check_content_section_key",
        ),
        Index("idx_site_content_lookup", "site_id", "section_key", "display_order"),
    )


class SiteProCon(Base):
    """Structured evaluation points (pro or con) with evidence and confidence."""

    __tablename__ = "site_pros_cons"

    point_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("landing_sites.site_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    point_type: Mapped[str] = mapped_column(String(3), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_note: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[int | None] = mapped_column(BigInteger)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    site: Mapped["LandingSite"] = relationship("LandingSite", back_populates="pros_cons")

    __table_args__ = (
        CheckConstraint("point_type IN ('PRO', 'CON')", name="check_pro_con_type"),
        Index("idx_site_pros_cons_display", "site_id", "point_type", "display_order"),
    )


class SiteMedia(Base):
    """Media assets attached to a landing site, stored outside PostgreSQL."""

    __tablename__ = "site_media"

    media_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("landing_sites.site_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    media_type: Mapped[str] = mapped_column(String(50), default="image")
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_path: Mapped[str | None] = mapped_column(Text)
    original_filename: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width_px: Mapped[int | None] = mapped_column(Integer)
    height_px: Mapped[int | None] = mapped_column(Integer)
    caption: Mapped[str | None] = mapped_column(Text)
    credit: Mapped[str | None] = mapped_column(Text)
    alt_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_id: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    site: Mapped["LandingSite"] = relationship("LandingSite", back_populates="media")

    __table_args__ = (
        CheckConstraint(
            "media_type IN ('image', 'map', 'chart', 'other')",
            name="check_media_type",
        ),
        Index("idx_site_media_display", "site_id", "display_order"),
    )


class SiteHistory(Base):
    """Historical missions, observation milestones, or discovery events."""

    __tablename__ = "site_history"

    history_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("landing_sites.site_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_date: Mapped[date | None] = mapped_column(Date)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[int | None] = mapped_column(BigInteger)
    display_order: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    site: Mapped["LandingSite"] = relationship("LandingSite", back_populates="history_events")

    __table_args__ = (Index("idx_site_history_order", "site_id", "display_order"),)
