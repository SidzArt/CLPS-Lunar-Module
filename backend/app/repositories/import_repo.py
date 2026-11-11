"""SQLAlchemy repository for staging imports and audit tracking."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.provenance import DatasetImport, ImportRow


def list_imports(
    db: Session,
    *,
    status_filter: str | None = None,
    limit: int = 50,
) -> tuple[list[DatasetImport], int]:
    """Return dataset import jobs ordered newest first with total count."""
    stmt = select(DatasetImport)
    if status_filter:
        stmt = stmt.where(DatasetImport.status == status_filter)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = list(
        db.scalars(
            stmt.order_by(DatasetImport.started_at.desc(), DatasetImport.import_id.desc()).limit(
                max(1, min(limit, 200))
            )
        ).all()
    )
    return rows, int(total)


def create_import(
    db: Session,
    filename: str,
    source_id: int | None = None,
    admin_id: str | None = None,
) -> DatasetImport:
    """Create staging import record."""
    imp = DatasetImport(
        filename=filename,
        source_id=source_id,
        imported_by_admin_id=admin_id,
        status="staged",
    )
    db.add(imp)
    db.flush()
    return imp


def get_import(db: Session, import_id: int) -> DatasetImport | None:
    """Retrieve import by ID."""
    return db.get(DatasetImport, import_id)


def create_import_row(
    db: Session,
    import_id: int,
    raw_record: dict,
    external_record_id: str | None = None,
) -> ImportRow:
    """Stage an individual row."""
    row = ImportRow(
        import_id=import_id,
        raw_record=raw_record,
        external_record_id=external_record_id,
        row_status="pending",
    )
    db.add(row)
    db.flush()
    return row


def get_import_rows(db: Session, import_id: int) -> list[ImportRow]:
    """Retrieve all staged rows for an import."""
    stmt = (
        select(ImportRow)
        .where(ImportRow.import_id == import_id)
        .order_by(ImportRow.import_row_id.asc())
    )
    return list(db.scalars(stmt).all())
