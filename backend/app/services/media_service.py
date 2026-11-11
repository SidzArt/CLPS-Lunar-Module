"""Service for secure image validation, WebP conversion, thumbnail generation, and storage."""

import contextlib
import hashlib
import io
import os
import uuid

from PIL import Image, ImageOps

from app.core.config import settings

# Restrict maximum pixel count to protect against decompression bombs
Image.MAX_IMAGE_PIXELS = 50_000_000

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB


def validate_and_process_image(
    file_bytes: bytes,
    original_filename: str,
) -> tuple[str, str, int, int, str, int]:
    """Validate file signatures, convert to WebP, generate thumbnail, and save to storage/media/.

    Returns:
        (file_path, thumbnail_path, width_px, height_px, sha256_hash, file_size_bytes)
    """
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"File size exceeds maximum allowed limit of {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB."
        )

    # Compute SHA-256 of raw uploaded payload
    sha256_hash = hashlib.sha256(file_bytes).hexdigest()

    # Open image with Pillow to verify genuine signature
    try:
        image = Image.open(io.BytesIO(file_bytes))
        image_format = image.format
        if image_format not in ALLOWED_FORMATS:
            raise ValueError(
                f"Unsupported image format '{image_format}'. Allowed: {', '.join(ALLOWED_FORMATS)}."
            )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Invalid or corrupted image file signature.") from exc

    # Ensure storage directory exists
    os.makedirs(settings.MEDIA_ROOT, exist_ok=True)

    # Correct image orientation if EXIF tag exists
    oriented_image = ImageOps.exif_transpose(image)
    rgb_image = oriented_image.convert("RGB")

    width_px, height_px = rgb_image.size

    # Resize main image if larger than 2560x1440 max dimension
    max_dim = 2560
    if width_px > max_dim or height_px > max_dim:
        rgb_image.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        width_px, height_px = rgb_image.size

    # Generate random unique filename
    storage_uuid = uuid.uuid4().hex
    main_filename = f"{storage_uuid}.webp"
    thumb_filename = f"{storage_uuid}_thumb.webp"

    main_abs_path = os.path.join(settings.MEDIA_ROOT, main_filename)
    thumb_abs_path = os.path.join(settings.MEDIA_ROOT, thumb_filename)

    # Save main WebP
    rgb_image.save(main_abs_path, format="WEBP", quality=85, method=6)
    saved_size_bytes = os.path.getsize(main_abs_path)

    # Generate and save square thumbnail (320x320)
    thumb_image = ImageOps.fit(rgb_image, (320, 320), Image.Resampling.LANCZOS)
    thumb_image.save(thumb_abs_path, format="WEBP", quality=80, method=6)

    # Relative paths for storage in database
    rel_main_path = os.path.join("media", main_filename)
    rel_thumb_path = os.path.join("media", thumb_filename)

    return rel_main_path, rel_thumb_path, width_px, height_px, sha256_hash, saved_size_bytes


def delete_media_files(file_path: str, thumbnail_path: str | None) -> None:
    """Safely unlink media files from filesystem outside webroot."""
    for rel_path in [file_path, thumbnail_path]:
        if not rel_path:
            continue
        # Prevent path traversal
        clean_filename = os.path.basename(rel_path)
        full_path = os.path.join(settings.MEDIA_ROOT, clean_filename)
        if os.path.exists(full_path) and os.path.isfile(full_path):
            with contextlib.suppress(OSError):
                os.remove(full_path)
