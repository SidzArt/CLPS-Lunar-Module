"""Service for multi-format dataset import staging, validation, preview, commit, and rollback."""

import csv
import io
import json
import math
import os
import re
import time
from typing import Any

import openpyxl
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.catalogue import LandingSite, NASARegion
from app.models.provenance import DatasetImport
from app.repositories import import_repo, site_repo
from app.schemas.imports import (
    ImportCommitOut,
    ImportPreviewOut,
    ImportRollbackOut,
    ImportRowPreview,
)

MOON_RADIUS_KM = 1737.4


def slugify(text: str) -> str:
    """Generate a clean URL slug from string."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


def calculate_lunar_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle surface distance in kilometers on the Moon."""
    phi1, lambda1 = math.radians(lat1), math.radians(lon1)
    phi2, lambda2 = math.radians(lat2), math.radians(lon2)
    # Spherical law of cosines
    cos_angle = math.sin(phi1) * math.sin(phi2) + math.cos(phi1) * math.cos(phi2) * math.cos(
        lambda1 - lambda2
    )
    cos_angle = max(-1.0, min(1.0, cos_angle))
    return MOON_RADIUS_KM * math.acos(cos_angle)


def parse_csv_file(file_bytes: bytes) -> list[dict[str, Any]]:
    """Parse raw CSV bytes into a list of row dictionaries."""
    try:
        text_content = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV file must be UTF-8 encoded.") from exc
    reader = csv.DictReader(io.StringIO(text_content))
    return [dict(row) for row in reader]


def parse_xlsx_file(file_bytes: bytes) -> list[dict[str, Any]]:
    """Parse raw XLSX bytes using openpyxl."""
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    except Exception as exc:
        raise ValueError("Invalid or corrupted XLSX workbook.") from exc
    sheet = workbook.active
    if sheet is None:
        return []
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(h).strip() if h is not None else f"col_{i}" for i, h in enumerate(rows[0])]
    records = []
    for row in rows[1:]:
        if all(cell is None for cell in row):
            continue
        record = {headers[i]: row[i] for i in range(min(len(headers), len(row)))}
        records.append(record)
    return records


def parse_geojson_file(file_bytes: bytes) -> list[dict[str, Any]]:
    """Parse GeoJSON FeatureCollection containing Point geometries."""
    try:
        data = json.loads(file_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid UTF-8 or malformed JSON in GeoJSON dataset.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("features", []), list):
        raise TypeError("GeoJSON payload must be a FeatureCollection object with 'features' list.")
    features = data.get("features", [])
    records = []
    for feat in features:
        if not isinstance(feat, dict):
            continue
        props = dict(feat.get("properties") or {})
        geometry = feat.get("geometry") or {}
        coords = geometry.get("coordinates", []) if isinstance(geometry, dict) else []
        if isinstance(geometry, dict) and geometry.get("type") == "Point" and len(coords) >= 2:
            # GeoJSON coordinates are [longitude, latitude, (elevation)]
            props["longitude"] = coords[0]
            props["latitude"] = coords[1]
            if len(coords) > 2:
                props["elevation"] = coords[2]
        records.append(props)
    return records


def stage_and_parse_dataset(
    db: Session,
    file_bytes: bytes,
    filename: str,
    admin_id: str | None = None,
    source_id: int | None = None,
) -> DatasetImport:
    """Stage uploaded file and insert unparsed rows into import_rows."""
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".csv":
        parsed_records = parse_csv_file(file_bytes)
    elif ext in (".xlsx", ".xls"):
        parsed_records = parse_xlsx_file(file_bytes)
    elif ext in (".geojson", ".json"):
        parsed_records = parse_geojson_file(file_bytes)
    else:
        raise ValueError(f"Unsupported file format '{ext}'. Supported: .csv, .xlsx, .geojson")

    # Save staged file copy under configured IMPORT_STAGING_ROOT
    os.makedirs(settings.IMPORT_STAGING_ROOT, exist_ok=True)
    safe_name = os.path.basename(filename)
    staged_path = os.path.join(
        settings.IMPORT_STAGING_ROOT, f"import_{int(time.time())}_{safe_name}"
    )
    with open(staged_path, "wb") as f:
        f.write(file_bytes)

    dataset_import = import_repo.create_import(
        db, filename=filename, source_id=source_id, admin_id=admin_id
    )

    for record in parsed_records:
        ext_id = (
            str(record.get("external_id") or record.get("id") or record.get("site_code") or "")
            or None
        )
        import_repo.create_import_row(
            db, import_id=dataset_import.import_id, raw_record=record, external_record_id=ext_id
        )

    db.commit()
    return dataset_import


def validate_import_dataset(db: Session, import_id: int) -> ImportPreviewOut:
    """Validate staged rows, detect duplicates, and generate preview without committing to catalogue."""
    dataset_import = import_repo.get_import(db, import_id)
    if not dataset_import:
        raise ValueError(f"Import {import_id} not found.")

    staged_rows = import_repo.get_import_rows(db, import_id)
    existing_sites = list(db.scalars(select(LandingSite)).all())
    existing_regions = list(db.scalars(select(NASARegion)).all())

    # Map regions for lookup
    region_map_by_code = {r.region_code.lower(): r for r in existing_regions if r.region_code}
    region_map_by_name = {r.region_name.lower(): r for r in existing_regions}

    valid_count = 0
    invalid_count = 0
    new_sites_count = 0
    updated_sites_count = 0
    row_previews: list[ImportRowPreview] = []

    for row in staged_rows:
        rec = row.raw_record
        errors: dict[str, str] = {}

        # 1. Site Code & Name
        site_code = str(rec.get("site_code") or rec.get("code") or rec.get("id") or "").strip()
        site_name = str(rec.get("site_name") or rec.get("name") or "").strip()

        if not site_code:
            errors["site_code"] = "Missing required site_code/code field."
        if not site_name:
            errors["site_name"] = "Missing required site_name/name field."

        # 2. Coordinates
        lat_raw = rec.get("latitude") or rec.get("lat") or rec.get("latitude_deg")
        lon_raw = rec.get("longitude") or rec.get("lon") or rec.get("longitude_deg")

        lat: float | None = None
        lon: float | None = None

        try:
            if lat_raw is None:
                errors["latitude"] = "Missing latitude coordinate."
            else:
                lat = float(lat_raw)
                if not (-90.0 <= lat <= 90.0):
                    errors["latitude"] = f"Latitude {lat} out of range [-90, +90]."
        except (ValueError, TypeError):
            errors["latitude"] = f"Invalid numeric latitude: {lat_raw}"

        try:
            if lon_raw is None:
                errors["longitude"] = "Missing longitude coordinate."
            else:
                lon = float(lon_raw)
                if not (-180.0 <= lon <= 180.0):
                    errors["longitude"] = f"Longitude {lon} out of range [-180, +180]."
        except (ValueError, TypeError):
            errors["longitude"] = f"Invalid numeric longitude: {lon_raw}"

        # 3. Elevation check
        elev_raw = rec.get("elevation") or rec.get("elevation_m")
        if elev_raw is not None and str(elev_raw).strip() != "":
            try:
                float(elev_raw)
            except (ValueError, TypeError):
                errors["elevation"] = f"Invalid numeric elevation: {elev_raw}"

        # 4. Region matching
        reg_raw = str(rec.get("region") or rec.get("region_code") or "").strip().lower()
        if reg_raw and not (region_map_by_code.get(reg_raw) or region_map_by_name.get(reg_raw)):
            errors["region"] = f"Unrecognized region '{reg_raw}'."

        # 5. Duplicate Detection & Action Type
        action_type = "INSERT"
        matched_site = None
        if site_code:
            # Check exact site code match
            for s in existing_sites:
                if s.site_code.lower() == site_code.lower():
                    matched_site = s
                    action_type = "UPDATE"
                    break

        # Coordinate proximity check against existing sites
        if lat is not None and lon is not None and not matched_site:
            for s in existing_sites:
                dist_km = calculate_lunar_distance_km(
                    lat, lon, float(s.latitude_deg), float(s.longitude_deg)
                )
                if dist_km < 0.2:  # within 200m
                    errors["coordinate_proximity_warning"] = (
                        f"Proximity conflict: within {dist_km * 1000:.1f}m of existing site '{s.site_name}' ({s.site_code})."
                    )

        if errors:
            row.row_status = "invalid"
            row.validation_errors = errors
            invalid_count += 1
            action_type = "REJECT"
        else:
            row.row_status = "valid"
            row.validation_errors = None
            valid_count += 1
            if action_type == "INSERT":
                new_sites_count += 1
            else:
                updated_sites_count += 1

        row_previews.append(
            ImportRowPreview(
                row_id=row.import_row_id,
                row_status=row.row_status,
                site_code=site_code or None,
                site_name=site_name or None,
                latitude_deg=lat,
                longitude_deg=lon,
                action_type=action_type,
                validation_errors=errors or None,
            )
        )

    # Update import status to previewed
    counts_summary = {
        "total": len(staged_rows),
        "valid": valid_count,
        "invalid": invalid_count,
        "new_sites": new_sites_count,
        "updated_sites": updated_sites_count,
    }
    dataset_import.status = "previewed"
    dataset_import.row_counts = counts_summary
    db.commit()

    return ImportPreviewOut(
        import_id=import_id,
        filename=dataset_import.filename,
        status="previewed",
        total_rows=len(staged_rows),
        valid_rows_count=valid_count,
        invalid_rows_count=invalid_count,
        new_sites_count=new_sites_count,
        updated_sites_count=updated_sites_count,
        rows=row_previews,
    )


def commit_import_dataset(db: Session, import_id: int) -> ImportCommitOut:
    """Transactionally commit all valid staged rows to the live landing_sites catalogue."""
    dataset_import = import_repo.get_import(db, import_id)
    if not dataset_import:
        raise ValueError(f"Import {import_id} not found.")

    if dataset_import.status not in ("staged", "previewed"):
        raise ValueError(f"Cannot commit import in status '{dataset_import.status}'.")

    # Re-validate to guarantee up-to-date state
    validate_import_dataset(db, import_id)
    staged_rows = import_repo.get_import_rows(db, import_id)

    existing_regions = list(db.scalars(select(NASARegion)).all())
    region_map_by_code = {
        r.region_code.lower(): r.region_id for r in existing_regions if r.region_code
    }
    region_map_by_name = {r.region_name.lower(): r.region_id for r in existing_regions}

    start_time = time.perf_counter()
    committed_sites = 0

    try:
        for row in staged_rows:
            if row.row_status != "valid":
                continue

            rec = row.raw_record
            site_code = str(rec.get("site_code") or rec.get("code") or rec.get("id")).strip()
            site_name = str(rec.get("site_name") or rec.get("name")).strip()
            lat_raw = rec.get("latitude") or rec.get("lat") or rec.get("latitude_deg")
            lon_raw = rec.get("longitude") or rec.get("lon") or rec.get("longitude_deg")
            lat = float(str(lat_raw))
            lon = float(str(lon_raw))

            elev_raw = rec.get("elevation") or rec.get("elevation_m")
            elevation_m = (
                float(elev_raw) if elev_raw is not None and str(elev_raw).strip() != "" else None
            )

            terrain_type = str(rec.get("terrain_type") or "").strip() or None
            overview_summary = (
                str(rec.get("overview_summary") or rec.get("description") or "").strip() or None
            )
            catalogue_status = str(rec.get("catalogue_status") or "draft").strip().lower()

            reg_raw = str(rec.get("region") or rec.get("region_code") or "").strip().lower()
            region_id = region_map_by_code.get(reg_raw) or region_map_by_name.get(reg_raw)

            # Check if site exists
            existing_site = site_repo.get_site_by_code(db, site_code)
            if existing_site:
                # Snapshot pre-update attributes so rollback restores without deleting existing site
                prior_snapshot = {
                    "site_name": existing_site.site_name,
                    "latitude_deg": float(existing_site.latitude_deg),
                    "longitude_deg": float(existing_site.longitude_deg),
                    "elevation_m": existing_site.elevation_m,
                    "terrain_type": existing_site.terrain_type,
                    "overview_summary": existing_site.overview_summary,
                    "region_id": existing_site.region_id,
                }
                existing_site.site_name = site_name
                existing_site.latitude_deg = lat
                existing_site.longitude_deg = lon
                if elevation_m is not None:
                    existing_site.elevation_m = elevation_m
                if terrain_type:
                    existing_site.terrain_type = terrain_type
                if overview_summary:
                    existing_site.overview_summary = overview_summary
                if region_id:
                    existing_site.region_id = region_id
                target_site = existing_site
                row.validation_errors = {"_rollback": {"action": "update", "prior": prior_snapshot}}
            else:
                # Create new site
                candidate_slug = slugify(site_code)
                # Ensure unique slug
                existing_slug = db.scalar(
                    select(LandingSite).where(LandingSite.site_slug == candidate_slug)
                )
                if existing_slug:
                    candidate_slug = f"{candidate_slug}-{int(time.time())}"

                target_site = site_repo.create_site(
                    db,
                    {
                        "site_code": site_code,
                        "site_slug": candidate_slug,
                        "site_name": site_name,
                        "region_id": region_id,
                        "latitude_deg": lat,
                        "longitude_deg": lon,
                        "elevation_m": elevation_m,
                        "terrain_type": terrain_type,
                        "overview_summary": overview_summary,
                        "catalogue_status": catalogue_status
                        if catalogue_status in ("draft", "verified", "published")
                        else "draft",
                    },
                )
                row.validation_errors = {"_rollback": {"action": "insert"}}

            # Link import row to site and update row_status
            row.site_id = target_site.site_id
            row.row_status = "committed"
            committed_sites += 1

            # If row contains sections, stage them
            for section_key in ("overview", "history", "geology", "research"):
                section_body = rec.get(f"section_{section_key}") or rec.get(section_key)
                if section_body and str(section_body).strip():
                    site_repo.create_section(
                        db,
                        {
                            "site_id": target_site.site_id,
                            "section_key": section_key,
                            "title": section_key.capitalize(),
                            "body": str(section_body).strip(),
                            "display_order": 0,
                            "source_status": "verified",
                        },
                    )

            # If row contains pros / cons
            pro_text = rec.get("pro") or rec.get("pro_point")
            if pro_text and str(pro_text).strip():
                site_repo.create_pro_con(
                    db,
                    {
                        "site_id": target_site.site_id,
                        "point_type": "PRO",
                        "title": "Documented Advantage",
                        "body": str(pro_text).strip(),
                        "display_order": 0,
                    },
                )
            con_text = rec.get("con") or rec.get("con_point")
            if con_text and str(con_text).strip():
                site_repo.create_pro_con(
                    db,
                    {
                        "site_id": target_site.site_id,
                        "point_type": "CON",
                        "title": "Documented Limitation",
                        "body": str(con_text).strip(),
                        "display_order": 0,
                    },
                )

        dataset_import.status = "committed"
        db.commit()
    except Exception as exc:
        db.rollback()
        raise RuntimeError(f"Import commit transaction failed: {exc}") from exc

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    return ImportCommitOut(
        import_id=import_id,
        status="committed",
        committed_sites_count=committed_sites,
        committed_rows_count=committed_sites,
        execution_time_ms=round(elapsed_ms, 2),
        message=f"Successfully committed {committed_sites} landing site records to catalogue.",
    )


def rollback_import_dataset(db: Session, import_id: int) -> ImportRollbackOut:
    """Roll back committed import records or cancel uncommitted staging."""
    dataset_import = import_repo.get_import(db, import_id)
    if not dataset_import:
        raise ValueError(f"Import {import_id} not found.")

    staged_rows = import_repo.get_import_rows(db, import_id)
    rolled_back_count = 0

    if dataset_import.status == "committed":
        # Remove newly inserted sites or restore pre-existing updated sites
        for row in staged_rows:
            if row.site_id and row.row_status == "committed":
                site = db.get(LandingSite, row.site_id)
                meta = row.validation_errors if isinstance(row.validation_errors, dict) else {}
                raw_rb = meta.get("_rollback")
                rollback_meta = raw_rb if isinstance(raw_rb, dict) else {}
                action = rollback_meta.get("action")
                if site is not None and action == "update":
                    raw_prior = rollback_meta.get("prior")
                    prior = raw_prior if isinstance(raw_prior, dict) else {}
                    for field_name in (
                        "site_name",
                        "latitude_deg",
                        "longitude_deg",
                        "elevation_m",
                        "terrain_type",
                        "overview_summary",
                        "region_id",
                    ):
                        if field_name in prior:
                            setattr(site, field_name, prior[field_name])
                    rolled_back_count += 1
                elif site is not None:
                    db.delete(site)
                    rolled_back_count += 1
                row.row_status = "skipped"
        dataset_import.status = "rolled_back"
        db.commit()
        return ImportRollbackOut(
            import_id=import_id,
            status="rolled_back",
            rolled_back_sites_count=rolled_back_count,
            message=f"Reversed committed import across {rolled_back_count} landing site records.",
        )
    else:
        # Simply mark staged as cancelled/rolled_back
        dataset_import.status = "rolled_back"
        for row in staged_rows:
            row.row_status = "skipped"
        db.commit()
        return ImportRollbackOut(
            import_id=import_id,
            status="rolled_back",
            rolled_back_sites_count=0,
            message="Uncommitted staging import has been cancelled.",
        )
