"""SQLAlchemy models for research data sources, citations, and staged imports."""

from datetime import date, datetime

from sqlalchemy import (
    UUID,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DataSource(Base):
    """Authoritative scientific provenance, publication metadata, and citations."""

    __tablename__ = "data_sources"

    source_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agency_name: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    publisher: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    publication_date: Mapped[date | None] = mapped_column(Date)
    accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dataset_version: Mapped[str | None] = mapped_column(Text)
    licence: Mapped[str | None] = mapped_column(Text)
    citation_text: Mapped[str | None] = mapped_column(Text)
    checksum: Mapped[str | None] = mapped_column(Text)


class SiteSourceLink(Base):
    """Many-to-many link associating data sources with landing site facts."""

    __tablename__ = "site_source_links"

    link_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("landing_sites.site_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("data_sources.source_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relation_type: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class DatasetImport(Base):
    """Staging and audit record for dataset imports (CSV, XLSX, GeoJSON)."""

    __tablename__ = "dataset_imports"

    import_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("data_sources.source_id", ondelete="SET NULL")
    )
    imported_by_admin_id: Mapped[UUID | None] = mapped_column(UUID)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(50), default="staged", index=True)
    row_counts: Mapped[dict | None] = mapped_column(JSONB)
    error_report_path: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "status IN ('staged', 'validating', 'previewed', 'committed', 'rejected', 'rolled_back')",
            name="check_import_status",
        ),
    )


class ImportRow(Base):
    """Individual row-level staging record preserving raw import data and errors."""

    __tablename__ = "import_rows"

    import_row_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    import_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dataset_imports.import_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_record_id: Mapped[str | None] = mapped_column(Text)
    site_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("landing_sites.site_id", ondelete="SET NULL"), index=True
    )
    row_status: Mapped[str] = mapped_column(String(50), default="pending")
    raw_record: Mapped[dict] = mapped_column(JSONB, nullable=False)
    validation_errors: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        CheckConstraint(
            "row_status IN ('pending', 'valid', 'invalid', 'committed', 'skipped')",
            name="check_import_row_status",
        ),
    )
