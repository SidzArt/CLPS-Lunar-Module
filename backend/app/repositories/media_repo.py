"""SQLAlchemy repository for media asset database operations."""

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.catalogue import SiteMedia


def list_media_all(
    db: Session,
    *,
    site_id: int | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[SiteMedia], int]:
    """List uploaded media records filtered optionally by site_id."""
    stmt = select(SiteMedia)
    if site_id is not None:
        stmt = stmt.where(SiteMedia.site_id == site_id)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = list(
        db.scalars(
            stmt.order_by(
                SiteMedia.site_id.asc(), SiteMedia.display_order.asc(), SiteMedia.media_id.desc()
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return rows, int(total)


def create_media(db: Session, media_dict: dict) -> SiteMedia:
    """Store media record in PostgreSQL."""
    media = SiteMedia(**media_dict)
    db.add(media)
    db.flush()
    return media


def get_media_by_id(db: Session, media_id: int) -> SiteMedia | None:
    """Retrieve media asset by ID."""
    return db.get(SiteMedia, media_id)


def delete_media(db: Session, media: SiteMedia) -> None:
    """Delete media row from database."""
    db.delete(media)
    db.flush()


def set_primary_media(db: Session, site_id: int, media_id: int) -> SiteMedia | None:
    """Set specified media asset as primary for the site and unset others."""
    # Unset existing primary for this site
    db.execute(
        update(SiteMedia)
        .where(SiteMedia.site_id == site_id, SiteMedia.is_primary == True)
        .values(is_primary=False)
    )
    # Set target media as primary
    media = db.get(SiteMedia, media_id)
    if media and media.site_id == site_id:
        media.is_primary = True
        db.flush()
        return media
    return None


def update_media(db: Session, media: SiteMedia, update_data: dict) -> SiteMedia:
    """Update editable media metadata fields."""
    for key, value in update_data.items():
        if hasattr(media, key):
            setattr(media, key, value)
    db.flush()
    return media


def list_all_referenced_paths(db: Session) -> set[str]:
    """Return relative file paths referenced by site_media for orphan disk scanning."""
    rows = db.execute(select(SiteMedia.file_path, SiteMedia.thumbnail_path)).all()
    paths: set[str] = set()
    for file_path, thumb_path in rows:
        if file_path:
            paths.add(file_path)
        if thumb_path:
            paths.add(thumb_path)
    return paths
