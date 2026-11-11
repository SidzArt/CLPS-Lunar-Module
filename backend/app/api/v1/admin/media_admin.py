"""Admin endpoints for media asset listing, upload, metadata edit, primary selection, and deletion."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.audit import log_audit
from app.core.auth_dependency import RequireRole
from app.core.config import settings
from app.db.session import get_db
from app.models.admin import Admin
from app.models.catalogue import SiteMedia
from app.models.provenance import DataSource
from app.repositories import media_repo, site_repo
from app.schemas.admin_portal import AdminMediaListOut, MediaUpdateIn, OrphanMediaFileOut
from app.schemas.catalogue import SiteMediaOut
from app.services import media_service

router = APIRouter(prefix="/admin/media", tags=["Admin Media"])


def _serialize_media(media: SiteMedia) -> SiteMediaOut:
    return SiteMediaOut(
        media_id=media.media_id,
        site_id=media.site_id,
        media_type=media.media_type,
        image_url=f"/storage/{media.file_path}",
        thumbnail_url=f"/storage/{media.thumbnail_path}" if media.thumbnail_path else None,
        original_filename=media.original_filename,
        mime_type=media.mime_type,
        file_size_bytes=media.file_size_bytes,
        width_px=media.width_px,
        height_px=media.height_px,
        caption=media.caption,
        credit=media.credit,
        alt_text=media.alt_text,
        source_id=media.source_id,
        sha256=media.sha256,
        display_order=media.display_order,
        is_primary=media.is_primary,
        created_at=media.created_at,
    )


@router.get(
    "",
    response_model=AdminMediaListOut,
    summary="List uploaded media assets and scan storage for unreferenced orphan files",
)
def list_admin_media(
    _admin: Annotated[
        Admin, Depends(RequireRole("site_editor", "research_admin", "system_admin", "viewer"))
    ],
    db: Annotated[Session, Depends(get_db)],
    site_id: Annotated[int | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> AdminMediaListOut:
    """List site media assets along with non-referenced orphan files inside MEDIA_ROOT."""
    rows, total = media_repo.list_media_all(db, site_id=site_id, page=page, page_size=page_size)
    referenced = media_repo.list_all_referenced_paths(db)

    orphans: list[OrphanMediaFileOut] = []
    media_root = Path(settings.MEDIA_ROOT)
    if media_root.exists() and media_root.is_dir():
        for entry in sorted(media_root.iterdir()):
            if not entry.is_file() or entry.name.startswith("."):
                continue
            rel = f"media/{entry.name}"
            if rel not in referenced:
                orphans.append(
                    OrphanMediaFileOut(relative_path=rel, size_bytes=entry.stat().st_size)
                )

    return AdminMediaListOut(
        items=[_serialize_media(m).model_dump() for m in rows],
        total=total,
        orphan_files=orphans,
    )


@router.post(
    "/upload",
    response_model=SiteMediaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload site media asset",
    description="Validates image file signature, converts to WebP, creates thumbnail, and stores outside webroot.",
)
async def upload_site_media(
    site_id: Annotated[int, Form()],
    file: UploadFile,
    alt_text: Annotated[str, Form(...)],
    caption: Annotated[str | None, Form()] = None,
    credit: Annotated[str | None, Form()] = None,
    is_primary: Annotated[bool, Form()] = False,
    display_order: Annotated[int, Form()] = 0,
    admin: Admin = Depends(RequireRole("site_editor")),
    db: Session = Depends(get_db),
) -> SiteMediaOut:
    """Process image upload, generate WebP derivatives, and store metadata."""
    site = site_repo.get_site_by_id(db, site_id)
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Landing site with ID {site_id} was not found.",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    try:
        rel_path, thumb_path, width, height, sha256_hash, size_bytes = (
            media_service.validate_and_process_image(
                file_bytes=file_bytes,
                original_filename=file.filename or "uploaded_image",
            )
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # If this is marked primary, unset existing primary
    if is_primary:
        media_repo.set_primary_media(db, site_id, -1)

    media_dict = {
        "site_id": site_id,
        "media_type": "image",
        "file_path": rel_path,
        "thumbnail_path": thumb_path,
        "original_filename": file.filename,
        "mime_type": "image/webp",
        "file_size_bytes": size_bytes,
        "width_px": width,
        "height_px": height,
        "caption": caption,
        "credit": credit,
        "alt_text": alt_text,
        "sha256": sha256_hash,
        "display_order": display_order,
        "is_primary": is_primary,
    }

    media = media_repo.create_media(db, media_dict)
    log_audit(
        db,
        action_key="MEDIA_UPLOAD",
        entity_type="site_media",
        entity_id=str(media.media_id),
        admin_id=str(admin.admin_id),
        after_snapshot={"site_id": site_id, "file_path": rel_path, "sha256": sha256_hash},
    )
    db.commit()

    return _serialize_media(media)


@router.patch(
    "/{media_id}/primary",
    response_model=SiteMediaOut,
    summary="Set primary gallery image",
    description="Marks specified media asset as the primary thumbnail and cover image.",
)
def set_primary_image(
    media_id: int,
    admin: Annotated[Admin, Depends(RequireRole("site_editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> SiteMediaOut:
    """Set media as primary."""
    media = media_repo.get_media_by_id(db, media_id)
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Media asset with ID {media_id} was not found.",
        )

    updated = media_repo.set_primary_media(db, media.site_id, media_id)
    assert updated is not None

    log_audit(
        db,
        action_key="MEDIA_SET_PRIMARY",
        entity_type="site_media",
        entity_id=str(media_id),
        admin_id=str(admin.admin_id),
    )
    db.commit()

    return _serialize_media(updated)


@router.patch(
    "/{media_id}",
    response_model=SiteMediaOut,
    summary="Update media caption, attribution, alt text, type, or display order",
)
def update_media_metadata(
    media_id: int,
    payload: MediaUpdateIn,
    admin: Annotated[Admin, Depends(RequireRole("site_editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> SiteMediaOut:
    """Edit non-binary metadata attributes of a site media asset with audit trail."""
    media = media_repo.get_media_by_id(db, media_id)
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Media asset with ID {media_id} was not found.",
        )
    update_dict = payload.model_dump(exclude_unset=True)
    if (
        update_dict.get("source_id") is not None
        and db.get(DataSource, update_dict["source_id"]) is None
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Data source ID {update_dict['source_id']} was not found.",
        )
    before = {
        "caption": media.caption,
        "credit": media.credit,
        "alt_text": media.alt_text,
        "display_order": media.display_order,
    }
    updated = media_repo.update_media(db, media, update_dict)
    log_audit(
        db,
        action_key="MEDIA_UPDATE",
        entity_type="site_media",
        entity_id=str(media_id),
        admin_id=str(admin.admin_id),
        before_snapshot=before,
        after_snapshot=update_dict,
    )
    db.commit()
    db.refresh(updated)
    return _serialize_media(updated)


@router.delete(
    "/{media_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete media asset",
    description="Safely deletes media row from PostgreSQL and unlinks physical WebP files.",
)
def delete_media_asset(
    media_id: int,
    admin: Annotated[Admin, Depends(RequireRole("site_editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Delete media asset and remove associated files from disk."""
    media = media_repo.get_media_by_id(db, media_id)
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Media asset with ID {media_id} was not found.",
        )

    file_path = media.file_path
    thumb_path = media.thumbnail_path

    media_repo.delete_media(db, media)
    log_audit(
        db,
        action_key="MEDIA_DELETE",
        entity_type="site_media",
        entity_id=str(media_id),
        admin_id=str(admin.admin_id),
    )
    db.commit()

    # Safely remove physical files
    media_service.delete_media_files(file_path, thumb_path)

    return {"status": "DELETED", "message": f"Media asset {media_id} deleted successfully."}
