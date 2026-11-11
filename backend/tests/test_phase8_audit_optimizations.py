"""Phase 8 verification tests covering bug fixes, query optimizations, and scientific invariants."""

from __future__ import annotations

import io
import uuid

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import event

from app.db.session import SessionLocal, engine
from app.models.catalogue import LandingSite, NASARegion, SiteContent
from app.models.operations import BackgroundJob
from app.services.geometry import (
    cartesian_enu_basis,
    lat_lon_elev_to_cartesian_m,
    normalize_longitude_deg,
)
from app.services.search_service import search_sites
from app.services.visibility import HorizonProfileData
from app.worker.simulation_worker import _mark_job_failed


def test_search_fts_batches_site_lookups_without_n_plus_one() -> None:
    """FTS search loads matching LandingSite + region in one batched query instead of N+1."""
    unique_token = f"phase8fts{uuid.uuid4().hex[:8]}"
    created_ids: list[int] = []
    region_id: int | None = None

    with SessionLocal() as db:
        region = NASARegion(
            region_code=f"P8-{uuid.uuid4().hex[:6]}",
            region_name="Phase 8 Test Basin",
            description="Ephemeral region for FTS batch query test.",
        )
        db.add(region)
        db.flush()
        region_id = region.region_id

        for idx in range(3):
            site = LandingSite(
                site_code=f"P8-FTS-{idx}-{uuid.uuid4().hex[:5]}",
                site_slug=f"p8-fts-{idx}-{uuid.uuid4().hex[:5]}",
                site_name=f"Phase8 Batch Candidate {idx}",
                region_id=region_id,
                latitude_deg=-80.0 - idx * 0.2,
                longitude_deg=20.0 + idx * 0.5,
                elevation_m=1500.0,
                terrain_type="Highland Ridge",
                overview_summary="FTS query batch verification site.",
                catalogue_status="published",
            )
            db.add(site)
            db.flush()
            created_ids.append(site.site_id)
            db.add(
                SiteContent(
                    site_id=site.site_id,
                    section_key="geology",
                    title="Geology",
                    body=f"Unique spectral signature {unique_token} measured in crater regolith.",
                    display_order=1,
                    language_code="en",
                    source_status="verified",
                )
            )
        db.commit()

    executed_sql: list[str] = []

    def _count_sql(
        _conn: object,
        _cursor: object,
        statement: str,
        _params: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        executed_sql.append(statement)

    try:
        with SessionLocal() as db:
            event.listen(engine, "before_cursor_execute", _count_sql)
            try:
                hits = search_sites(db, unique_token, limit=10)
            finally:
                event.remove(engine, "before_cursor_execute", _count_sql)

        assert len(hits) == 3
        assert all(h.match_field == "content" for h in hits)
        assert all(h.region_name == "Phase 8 Test Basin" for h in hits)
        # Expect 1 direct name query + 1 FTS query + 1 batched IN query = 3 SQL statements total
        assert len(executed_sql) == 3, f"Expected 3 batched queries, saw {len(executed_sql)}"
    finally:
        with SessionLocal() as cleanup:
            for sid in created_ids:
                obj = cleanup.get(LandingSite, sid)
                if obj:
                    cleanup.delete(obj)
            if region_id is not None:
                reg = cleanup.get(NASARegion, region_id)
                if reg:
                    cleanup.delete(reg)
            cleanup.commit()


def test_site_sub_endpoints_avoid_duplicate_slug_lookup(client: TestClient) -> None:
    """Public site sub-endpoints resolve site_id once instead of reloading full detail twice."""
    site_slug = f"p8-sub-{uuid.uuid4().hex[:8]}"
    site_id: int | None = None
    with SessionLocal() as db:
        site = LandingSite(
            site_code=f"P8-SUB-{uuid.uuid4().hex[:6]}",
            site_slug=site_slug,
            site_name="Phase8 Subendpoint Site",
            latitude_deg=12.0,
            longitude_deg=-15.0,
            catalogue_status="published",
        )
        db.add(site)
        db.commit()
        db.refresh(site)
        site_id = site.site_id

    executed_sql: list[str] = []

    def _capture(
        _conn: object,
        _cursor: object,
        statement: str,
        _params: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        executed_sql.append(statement)

    try:
        for suffix in ("sections", "pros-cons", "metrics", "media", "history"):
            executed_sql.clear()
            event.listen(engine, "before_cursor_execute", _capture)
            try:
                resp = client.get(f"/api/v1/sites/{site_slug}/{suffix}")
            finally:
                event.remove(engine, "before_cursor_execute", _capture)
            assert resp.status_code == 200
            assert len(executed_sql) == 2, (
                f"Expected 2 queries for /{suffix}, saw {len(executed_sql)}: {executed_sql}"
            )

        miss = client.get("/api/v1/sites/does-not-exist-p8/sections")
        assert miss.status_code == 404
    finally:
        if site_id is not None:
            with SessionLocal() as cleanup:
                obj = cleanup.get(LandingSite, site_id)
                if obj:
                    cleanup.delete(obj)
                    cleanup.commit()


def test_horizon_profile_precomputed_circular_interpolation() -> None:
    """HorizonProfileData precomputes wrapped arrays and interpolates seamlessly across 360 deg."""
    profile = HorizonProfileData(
        azimuths_deg=np.array([10.0, 100.0, 190.0, 280.0], dtype=np.float64),
        elevations_deg=np.array([4.0, 8.0, 2.0, 6.0], dtype=np.float64),
        quality_state="verified_terrain_aware",
        azimuth_bins=4,
    )
    assert profile._az_ext.size == 5
    # Exact wrap midpoint between 280 deg (6 deg) and 10+360=370 deg (4 deg) is 325 deg -> 5.0 deg
    assert np.isclose(profile.interpolate(325.0), 5.0, atol=1e-9)
    # Azimuth strictly before first bin center (e.g. 365 % 360 = 5 deg -> midway 280..370 + 45 => 4.111...)
    assert 4.0 < profile.interpolate(5.0) < 6.0

    empty_profile = HorizonProfileData(
        azimuths_deg=np.empty(0, dtype=np.float64),
        elevations_deg=np.empty(0, dtype=np.float64),
        quality_state="geometric_only",
        azimuth_bins=0,
        default_horizon_deg=1.25,
    )
    assert empty_profile.interpolate(123.0) == 1.25


def test_simulation_worker_marks_invalid_payload_job_failed() -> None:
    """_mark_job_failed transitions malformed claimed jobs into terminal FAILED status."""
    with SessionLocal() as db:
        job = BackgroundJob(
            job_type="simulation_run",
            status="RUNNING",
            payload={},
            attempts=1,
            max_attempts=3,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.job_id

    try:
        _mark_job_failed(job_id, "Job payload missing simulation_id")
        with SessionLocal() as check_db:
            reloaded = check_db.get(BackgroundJob, job_id)
            assert reloaded is not None
            assert reloaded.status == "FAILED"
            assert reloaded.error_summary == "Job payload missing simulation_id"
    finally:
        with SessionLocal() as cleanup:
            reloaded = cleanup.get(BackgroundJob, job_id)
            if reloaded:
                cleanup.delete(reloaded)
                cleanup.commit()


def test_imports_reject_malformed_encodings_and_oversized_payloads(
    client: TestClient,
    admin_auth_headers: dict[str, str],
) -> None:
    """Malformed UTF-8 CSV, bad XLSX, malformed GeoJSON, and >15MB payloads return clean 400."""
    bad_csv = client.post(
        "/api/v1/admin/imports",
        headers=admin_auth_headers,
        files={"file": ("bad_utf8.csv", b"\xff\xfe\xfdinvalid_utf8", "text/csv")},
    )
    assert bad_csv.status_code == 400
    assert "UTF-8" in bad_csv.json()["detail"]

    bad_xlsx = client.post(
        "/api/v1/admin/imports",
        headers=admin_auth_headers,
        files={"file": ("corrupt.xlsx", b"not-a-valid-zip-workbook", "application/octet-stream")},
    )
    assert bad_xlsx.status_code == 400
    assert "XLSX" in bad_xlsx.json()["detail"]

    bad_geojson = client.post(
        "/api/v1/admin/imports",
        headers=admin_auth_headers,
        files={
            "file": (
                "bad.geojson",
                b'{"type":"FeatureCollection","features":"oops"}',
                "application/json",
            )
        },
    )
    assert bad_geojson.status_code == 400
    assert "FeatureCollection" in bad_geojson.json()["detail"]

    oversized = client.post(
        "/api/v1/admin/imports",
        headers=admin_auth_headers,
        files={"file": ("huge.csv", b"a" * (15 * 1024 * 1024 + 1), "text/csv")},
    )
    assert oversized.status_code == 400
    assert "15MB" in oversized.json()["detail"]


def test_media_upload_distinguishes_unsupported_format_from_corrupted_bytes(
    client: TestClient,
    admin_auth_headers: dict[str, str],
) -> None:
    """Valid BMP image gets explicit unsupported-format error instead of generic corruption error."""
    with SessionLocal() as db:
        site = LandingSite(
            site_code=f"P8-MED-{uuid.uuid4().hex[:6]}",
            site_slug=f"p8-med-{uuid.uuid4().hex[:6]}",
            site_name="Phase8 Media Validation Site",
            latitude_deg=0.0,
            longitude_deg=0.0,
            catalogue_status="draft",
        )
        db.add(site)
        db.commit()
        db.refresh(site)
        site_id = site.site_id

    try:
        img = Image.new("RGB", (64, 64), color=(10, 20, 30))
        buf = io.BytesIO()
        img.save(buf, format="BMP")
        resp = client.post(
            "/api/v1/admin/media/upload",
            headers=admin_auth_headers,
            data={"site_id": site_id, "alt_text": "BMP format check"},
            files={"file": ("sample.bmp", buf.getvalue(), "image/bmp")},
        )
        assert resp.status_code == 400
        assert "Unsupported image format" in resp.json()["detail"]
    finally:
        with SessionLocal() as cleanup:
            obj = cleanup.get(LandingSite, site_id)
            if obj:
                cleanup.delete(obj)
                cleanup.commit()


def test_lunar_coordinate_helpers_preserve_orthonormality_and_range() -> None:
    """normalize_longitude_deg wraps to [-180, 180] and cartesian_enu_basis is right-handed."""
    assert normalize_longitude_deg(180.0) == 180.0
    assert normalize_longitude_deg(270.0) == -90.0
    assert normalize_longitude_deg(-185.0) == 175.0

    xyz = lat_lon_elev_to_cartesian_m(-85.0, 31.6, 5000.0)
    east, north, up = cartesian_enu_basis(xyz)
    assert np.isclose(np.linalg.norm(east), 1.0, atol=1e-12)
    assert np.isclose(np.linalg.norm(north), 1.0, atol=1e-12)
    assert np.isclose(np.linalg.norm(up), 1.0, atol=1e-12)
    assert np.isclose(float(np.dot(east, north)), 0.0, atol=1e-12)
    assert np.isclose(float(np.dot(east, up)), 0.0, atol=1e-12)
    assert np.isclose(float(np.dot(north, up)), 0.0, atol=1e-12)
    det = float(np.linalg.det(np.column_stack([east, north, up])))
    assert np.isclose(det, 1.0, atol=1e-12)
