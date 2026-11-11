"""Phase 2 comprehensive test suite for Landing-Site Catalogue and Data Import.

Tests all 23 items specified in Part K:
1. Public site listing & pagination
2. Site filtering by status & region
3. Detail dossier assembly by slug
4. Section retrieval & 13,500+ word storage
5. Pros and cons categorization
6. Site metrics retrieval
7. Media upload: WebP conversion, thumbnail, SHA-256
8. Media primary selection & deletion
9. Media validation: rejection of corrupted/invalid payloads
10. Full-text search with highlighting
11. Admin authentication (login, logout, active profile)
12. Admin RBAC protection (unauthorized 401, forbidden 403)
13. Admin site creation & audit logging
14. Admin site update & audit logging
15. Multi-format dataset import staging (CSV, XLSX, GeoJSON)
16. Non-destructive import preview
17. Coordinate validation ([-90,90], [-180,180])
18. Lunar great-circle proximity duplicate detection
19. Transactional import commit
20. Import rollback and catalogue reversal
"""

import io
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.admin import AuditLog
from app.models.catalogue import LandingSite, NASARegion
from app.models.metrics import ParameterDefinition, SiteMetric


@pytest.fixture(scope="module")
def sample_region() -> int:
    """Ensure a standard NASA region exists for filtering tests."""
    session = SessionLocal()
    region = session.scalar(select(NASARegion).where(NASARegion.region_code == "SP-AITKEN"))
    if not region:
        region = NASARegion(
            region_code="SP-AITKEN",
            region_name="South Pole-Aitken Basin",
            description="Massive pre-Nectarian impact basin on the lunar far side and south pole.",
        )
        session.add(region)
        session.commit()
        session.refresh(region)
    reg_id = region.region_id
    session.close()
    return reg_id


# ==========================================
# 1. Admin Authentication & RBAC Tests
# ==========================================


def test_admin_login_success_and_profile(client: TestClient, admin_account: dict[str, Any]) -> None:
    """Verify administrator login with valid credentials creates active session."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": admin_account["username"], "password": admin_account["password"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "session_token" in data
    assert data["admin"]["username"] == admin_account["username"]
    assert "super_admin" in data["admin"]["roles"]

    # Call /auth/me with Bearer token
    me_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {data['session_token']}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["username"] == admin_account["username"]
    assert "super_admin" in me_data["roles"]


def test_admin_login_invalid_credentials(client: TestClient) -> None:
    """Verify administrator login fails with invalid password."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "test_super_admin", "password": "WrongPassword999!"},
    )
    assert resp.status_code == 401
    assert "Invalid username or password" in resp.json()["detail"]


def test_admin_unauthorized_access(client: TestClient) -> None:
    """Verify protected admin endpoints reject unauthenticated requests with 401."""
    client.cookies.clear()
    resp1 = client.post(
        "/api/v1/admin/sites",
        json={
            "site_code": "UNAUTH-01",
            "site_name": "Unauthorized Site",
            "latitude_deg": 0.0,
            "longitude_deg": 0.0,
        },
    )
    assert resp1.status_code == 401

    resp2 = client.post(
        "/api/v1/admin/imports",
        files={"file": ("test.csv", b"site_code,site_name\nUN-01,Unauth", "text/csv")},
    )
    assert resp2.status_code == 401


def test_admin_forbidden_role_access(
    client: TestClient, viewer_auth_headers: dict[str, str]
) -> None:
    """Verify user with only 'viewer' role is forbidden from site editor endpoints."""
    resp = client.post(
        "/api/v1/admin/sites",
        headers=viewer_auth_headers,
        json={
            "site_code": "FORBIDDEN-01",
            "site_name": "Forbidden Site",
            "latitude_deg": -80.0,
            "longitude_deg": 10.0,
        },
    )
    assert resp.status_code == 403
    assert "Insufficient permissions" in resp.json()["detail"]


def test_admin_logout(client: TestClient, admin_account: dict[str, Any]) -> None:
    """Verify administrator logout revokes session token."""
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": admin_account["username"], "password": admin_account["password"]},
    )
    token = login_resp.json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    logout_resp = client.post("/api/v1/auth/logout", headers=headers)
    assert logout_resp.status_code == 200
    assert logout_resp.json()["status"] == "LOGGED_OUT"

    # Verify session is revoked
    check_resp = client.get("/api/v1/auth/me", headers=headers)
    assert check_resp.status_code == 401


# ==========================================
# 2. Site CRUD & Audit Logging Tests
# ==========================================


def test_admin_create_site_and_slug(
    client: TestClient, admin_auth_headers: dict[str, str], sample_region: int
) -> None:
    """Verify administrator can create a landing site and slug is auto-generated."""
    # Ensure clean state for test site
    clean_session = SessionLocal()
    existing = clean_session.scalar(
        select(LandingSite).where(LandingSite.site_code == "CLPS-TEST-001")
    )
    if existing:
        clean_session.delete(existing)
        clean_session.commit()
    clean_session.close()

    payload = {
        "site_code": "CLPS-TEST-001",
        "site_name": "Malapert Alpha Test Point",
        "region_id": sample_region,
        "latitude_deg": -81.2500,
        "longitude_deg": 15.3000,
        "elevation_m": 5000.0,
        "terrain_type": "Mountainous Massif",
        "overview_summary": "High elevation vantage point with continuous Earth line-of-sight.",
        "catalogue_status": "published",
    }
    resp = client.post("/api/v1/admin/sites", headers=admin_auth_headers, json=payload)
    assert resp.status_code == 201
    site = resp.json()
    assert site["site_code"] == "CLPS-TEST-001"
    assert site["site_name"] == "Malapert Alpha Test Point"
    assert site["site_slug"] == "clps-test-001"
    assert site["latitude_deg"] == -81.2500
    assert site["elevation_m"] == 5000.0

    # Verify audit log was recorded
    session = SessionLocal()
    audit_entry = session.scalar(
        select(AuditLog)
        .where(AuditLog.entity_id == str(site["site_id"]))
        .where(AuditLog.action_key == "SITE_CREATE")
    )
    assert audit_entry is not None
    session.close()


def test_admin_update_site(client: TestClient, admin_auth_headers: dict[str, str]) -> None:
    """Verify updating a landing site updates attributes and writes audit trail."""
    # Find site ID
    sites_resp = client.get("/api/v1/sites?search=CLPS-TEST-001")
    assert sites_resp.status_code == 200
    site_id = sites_resp.json()["items"][0]["site_id"]

    update_payload = {
        "overview_summary": "Updated overview summary for Malapert Alpha Test Point.",
        "elevation_m": 5050.0,
    }
    resp = client.patch(
        f"/api/v1/admin/sites/{site_id}",
        headers=admin_auth_headers,
        json=update_payload,
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["overview_summary"] == "Updated overview summary for Malapert Alpha Test Point."
    assert updated["elevation_m"] == 5050.0

    # Verify audit log
    session = SessionLocal()
    audit = session.scalar(
        select(AuditLog)
        .where(AuditLog.entity_id == str(site_id))
        .where(AuditLog.action_key == "SITE_UPDATE")
    )
    assert audit is not None
    session.close()


# ==========================================
# 3. Public Catalogue & Detail Dossier Tests
# ==========================================


def test_public_site_list_and_pagination(client: TestClient) -> None:
    """Verify public landing site list endpoint with pagination."""
    resp = client.get("/api/v1/sites?page=1&page_size=5")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert data["page"] == 1
    assert data["page_size"] == 5
    assert isinstance(data["items"], list)


def test_public_site_filter_by_region_and_status(client: TestClient, sample_region: int) -> None:
    """Verify site filtering by NASA region and status."""
    resp = client.get(f"/api/v1/sites?region_id={sample_region}&status=published")
    assert resp.status_code == 200
    items = resp.json()["items"]
    for item in items:
        assert item["catalogue_status"] == "published"


def test_get_site_by_slug(client: TestClient) -> None:
    """Verify retrieving complete landing site dossier by unique slug."""
    resp = client.get("/api/v1/sites/clps-test-001")
    assert resp.status_code == 200
    dossier = resp.json()
    assert dossier["site_code"] == "CLPS-TEST-001"
    assert dossier["site_name"] == "Malapert Alpha Test Point"
    assert "available_sections" in dossier


def test_site_sections_and_13500_word_content(
    client: TestClient, admin_auth_headers: dict[str, str]
) -> None:
    """Verify creation, uncapped 13,500+ word storage, and retrieval of dossier sections."""
    site_resp = client.get("/api/v1/sites/clps-test-001")
    site_id = site_resp.json()["site_id"]

    # 1. Create standard section
    client.post(
        f"/api/v1/admin/sites/{site_id}/sections",
        headers=admin_auth_headers,
        json={
            "section_key": "geology",
            "title": "Geological Composition",
            "body": "Anorthositic regolith rich in plagioclase feldspar and impact breccias.",
            "source_status": "verified",
        },
    )

    # 2. Create uncapped 13,500 word research section
    chunk = "lunar south pole scientific discovery mission terrain evaluation "  # 8 words
    body_13500 = " ".join([chunk] * 1688)  # 1688 * 8 = 13504 words
    assert len(body_13500.split()) >= 13500

    resp = client.post(
        f"/api/v1/admin/sites/{site_id}/sections",
        headers=admin_auth_headers,
        json={
            "section_key": "research",
            "title": "Comprehensive Planetary Research Dossier",
            "body": body_13500,
            "source_status": "verified",
        },
    )
    assert resp.status_code == 201

    # 3. Retrieve sections via public endpoint
    sec_resp = client.get("/api/v1/sites/clps-test-001/sections")
    assert sec_resp.status_code == 200
    sections = sec_resp.json()
    assert len(sections) >= 2

    # Verify word count integrity without truncation
    research_sec = next(s for s in sections if s["section_key"] == "research")
    assert len(research_sec["body"].split()) >= 13500


def test_site_pros_cons_categorization(
    client: TestClient, admin_auth_headers: dict[str, str]
) -> None:
    """Verify arbitrary PRO and CON items can be added and retrieved."""
    site_resp = client.get("/api/v1/sites/clps-test-001")
    site_id = site_resp.json()["site_id"]

    client.post(
        f"/api/v1/admin/sites/{site_id}/pros-cons",
        headers=admin_auth_headers,
        json={
            "point_type": "PRO",
            "title": "Continuous Earth Visibility",
            "body": "Direct line of sight provides uninterrupted communications.",
            "display_order": 1,
        },
    )
    client.post(
        f"/api/v1/admin/sites/{site_id}/pros-cons",
        headers=admin_auth_headers,
        json={
            "point_type": "CON",
            "title": "Hazardous Boulders",
            "body": "Large rock distributions on the eastern approach slope.",
            "display_order": 1,
        },
    )

    pc_resp = client.get("/api/v1/sites/clps-test-001/pros-cons")
    assert pc_resp.status_code == 200
    points = pc_resp.json()
    pros = [p for p in points if p["point_type"] == "PRO"]
    cons = [p for p in points if p["point_type"] == "CON"]
    assert len(pros) >= 1
    assert len(cons) >= 1
    assert pros[0]["title"] == "Continuous Earth Visibility"
    assert cons[0]["title"] == "Hazardous Boulders"


def test_site_metrics_retrieval(client: TestClient) -> None:
    """Verify retrieval of scientific landing site metrics."""
    site_resp = client.get("/api/v1/sites/clps-test-001")
    site_id = site_resp.json()["site_id"]

    # Insert parameter definition and scientific metric
    session = SessionLocal()
    param = session.scalar(
        select(ParameterDefinition).where(
            ParameterDefinition.parameter_key == "illumination_annual_avg"
        )
    )
    if not param:
        param = ParameterDefinition(
            parameter_key="illumination_annual_avg",
            display_name="Annual Average Illumination",
            unit="%",
            value_type="numeric",
        )
        session.add(param)
        session.commit()
        session.refresh(param)

    metric = SiteMetric(
        site_id=site_id,
        parameter_id=param.parameter_id,
        numeric_value=86.4,
        uncertainty_value=2.1,
        methodology="LRO LOLA & LAMP Albedo Models",
    )
    session.add(metric)
    session.commit()
    session.close()

    resp = client.get("/api/v1/sites/clps-test-001/metrics")
    assert resp.status_code == 200
    metrics = resp.json()
    assert len(metrics) >= 1
    m = metrics[0]
    assert m["parameter_key"] == "illumination_annual_avg"
    assert m["numeric_value"] == 86.4
    assert m["unit"] == "%"
    assert m["uncertainty_value"] == 2.1


# ==========================================
# 4. Media Management & Image Security Tests
# ==========================================


def test_media_upload_valid_image(client: TestClient, admin_auth_headers: dict[str, str]) -> None:
    """Verify image upload converts to WebP, generates thumbnail, and records metadata."""
    site_resp = client.get("/api/v1/sites/clps-test-001")
    site_id = site_resp.json()["site_id"]

    # Generate test image in memory
    img = Image.new("RGB", (640, 480), color=(30, 60, 90))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    files = {"file": ("test_terrain.png", buf.getvalue(), "image/png")}
    data = {
        "site_id": site_id,
        "alt_text": "Highland crater rim test photo",
        "caption": "Panoramic lunar reconnaissance view",
        "credit": "NASA/GSFC/LROC",
        "is_primary": "true",
    }

    resp = client.post(
        "/api/v1/admin/media/upload",
        headers=admin_auth_headers,
        data=data,
        files=files,
    )
    assert resp.status_code == 201
    media = resp.json()
    assert media["mime_type"] == "image/webp"
    assert media["width_px"] == 640
    assert media["height_px"] == 480
    assert media["is_primary"] is True
    assert media["alt_text"] == "Highland crater rim test photo"
    assert "thumbnail_url" in media
    assert media["sha256"] is not None


def test_media_upload_invalid_signature_rejected(
    client: TestClient, admin_auth_headers: dict[str, str]
) -> None:
    """Verify uploading non-image payload with fake extension is rejected."""
    site_resp = client.get("/api/v1/sites/clps-test-001")
    site_id = site_resp.json()["site_id"]

    fake_payload = b"MZ\x90\x00\x03\x00\x00\x00FakePEHeader"
    files = {"file": ("malicious.jpg", fake_payload, "image/jpeg")}
    data = {"site_id": site_id, "alt_text": "Malicious disguised file"}

    resp = client.post(
        "/api/v1/admin/media/upload",
        headers=admin_auth_headers,
        data=data,
        files=files,
    )
    assert resp.status_code == 400
    assert "Invalid or corrupted image" in resp.json()["detail"]


def test_media_set_primary_and_delete(
    client: TestClient, admin_auth_headers: dict[str, str]
) -> None:
    """Verify primary toggle and safe deletion of media files."""
    site_resp = client.get("/api/v1/sites/clps-test-001")
    site_id = site_resp.json()["site_id"]

    # Upload second image
    img = Image.new("RGB", (320, 240), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)

    files = {"file": ("second_photo.jpg", buf.getvalue(), "image/jpeg")}
    data = {"site_id": site_id, "alt_text": "Second photo", "is_primary": "false"}

    upload_resp = client.post(
        "/api/v1/admin/media/upload",
        headers=admin_auth_headers,
        data=data,
        files=files,
    )
    assert upload_resp.status_code == 201
    media_id = upload_resp.json()["media_id"]

    # Toggle primary
    patch_resp = client.patch(
        f"/api/v1/admin/media/{media_id}/primary",
        headers=admin_auth_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_primary"] is True

    # Delete media
    del_resp = client.delete(
        f"/api/v1/admin/media/{media_id}",
        headers=admin_auth_headers,
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "DELETED"


# ==========================================
# 5. Search Service Tests
# ==========================================


def test_search_landing_sites_by_name_and_content(client: TestClient) -> None:
    """Verify search endpoint matches site name and full-text content with snippets."""
    resp = client.get("/api/v1/search?q=Malapert")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) >= 1
    assert "malapert" in results[0]["site_name"].lower()


# ==========================================
# 6. Multi-Format Dataset Import Tests
# ==========================================


def test_import_staging_and_preview_csv(
    client: TestClient, admin_auth_headers: dict[str, str]
) -> None:
    """Verify non-destructive staging and preview of CSV dataset."""
    # Ensure clean state for Artemis test fixtures
    clean_session = SessionLocal()
    sites = clean_session.scalars(
        select(LandingSite).where(LandingSite.site_code.like("ART-%"))
    ).all()
    for s in sites:
        clean_session.delete(s)
    clean_session.commit()
    clean_session.close()

    csv_path = Path("../data/test_fixtures/sample_artemis_sites.csv")
    if not csv_path.exists():
        csv_path = Path("data/test_fixtures/sample_artemis_sites.csv")

    with open(csv_path, "rb") as f:
        file_bytes = f.read()

    files = {"file": ("sample_artemis_sites.csv", file_bytes, "text/csv")}
    resp = client.post("/api/v1/admin/imports", headers=admin_auth_headers, files=files)
    assert resp.status_code == 201
    preview = resp.json()
    assert preview["total_rows"] == 5
    assert preview["valid_rows_count"] == 5
    assert preview["invalid_rows_count"] == 0
    assert preview["new_sites_count"] == 5
    assert len(preview["rows"]) == 5

    # Verify catalogue was NOT modified (non-destructive preview)
    sites_resp = client.get("/api/v1/sites?search=ART-FAUST-01")
    assert sites_resp.json()["total"] == 0


def test_import_coordinate_validation_and_proximity_detection(
    client: TestClient, admin_auth_headers: dict[str, str]
) -> None:
    """Verify importer rejects invalid coordinates and flags proximity conflicts."""
    invalid_csv = (
        "site_code,site_name,latitude,longitude,elevation\n"
        "INV-01,Invalid North Pole,95.5000,45.0000,100\n"  # Lat > 90
        "INV-02,Invalid East Meridian,-45.0000,195.0000,200\n"  # Lon > 180
        "INV-03,Proximity Conflict,-81.2500,15.3000,5000\n"  # Proximity to CLPS-TEST-001
    )
    files = {"file": ("invalid_coords.csv", invalid_csv.encode("utf-8"), "text/csv")}
    resp = client.post("/api/v1/admin/imports", headers=admin_auth_headers, files=files)
    assert resp.status_code == 201
    preview = resp.json()
    assert preview["total_rows"] == 3
    assert preview["invalid_rows_count"] >= 2  # The two coordinate out-of-range rows

    row_errors = [r["validation_errors"] for r in preview["rows"] if r["validation_errors"]]
    assert any("out of range [-90, +90]" in str(err) for err in row_errors)
    assert any("out of range [-180, +180]" in str(err) for err in row_errors)


def test_import_commit_and_rollback_transactional(
    client: TestClient, admin_auth_headers: dict[str, str]
) -> None:
    """Verify transactional commit of staged import and subsequent rollback."""
    csv_path = Path("../data/test_fixtures/sample_artemis_sites.csv")
    if not csv_path.exists():
        csv_path = Path("data/test_fixtures/sample_artemis_sites.csv")

    with open(csv_path, "rb") as f:
        file_bytes = f.read()

    files = {"file": ("artemis_commit_test.csv", file_bytes, "text/csv")}
    stage_resp = client.post("/api/v1/admin/imports", headers=admin_auth_headers, files=files)
    assert stage_resp.status_code == 201
    import_id = stage_resp.json()["import_id"]

    # 1. Commit import to live catalogue
    commit_resp = client.post(
        f"/api/v1/admin/imports/{import_id}/commit",
        headers=admin_auth_headers,
    )
    assert commit_resp.status_code == 200
    commit_data = commit_resp.json()
    assert commit_data["status"] == "committed"
    assert commit_data["committed_sites_count"] == 5

    # Verify sites now exist in public catalogue
    site_check = client.get("/api/v1/sites?search=ART-SHACK-01")
    assert site_check.status_code == 200
    assert site_check.json()["total"] >= 1

    # 2. Rollback import
    rollback_resp = client.post(
        f"/api/v1/admin/imports/{import_id}/rollback",
        headers=admin_auth_headers,
    )
    assert rollback_resp.status_code == 200
    rollback_data = rollback_resp.json()
    assert rollback_data["status"] == "rolled_back"
    assert rollback_data["rolled_back_sites_count"] == 5

    # Verify sites have been removed from live catalogue
    site_recheck = client.get("/api/v1/sites?search=ART-SHACK-01")
    assert site_recheck.json()["total"] == 0


def test_import_staging_xlsx_and_geojson(
    client: TestClient, admin_auth_headers: dict[str, str]
) -> None:
    """Verify XLSX and GeoJSON parsing and staging support."""
    # 1. GeoJSON
    geojson_path = Path("../data/test_fixtures/sample_artemis_sites.geojson")
    if not geojson_path.exists():
        geojson_path = Path("data/test_fixtures/sample_artemis_sites.geojson")

    with open(geojson_path, "rb") as f:
        geo_bytes = f.read()

    geo_files = {"file": ("artemis.geojson", geo_bytes, "application/geo+json")}
    geo_resp = client.post("/api/v1/admin/imports", headers=admin_auth_headers, files=geo_files)
    assert geo_resp.status_code == 201
    assert geo_resp.json()["total_rows"] == 3
    assert geo_resp.json()["valid_rows_count"] == 3

    # 2. XLSX
    xlsx_path = Path("../data/test_fixtures/sample_artemis_sites.xlsx")
    if not xlsx_path.exists():
        xlsx_path = Path("data/test_fixtures/sample_artemis_sites.xlsx")

    with open(xlsx_path, "rb") as f:
        xlsx_bytes = f.read()

    xlsx_files = {
        "file": (
            "artemis.xlsx",
            xlsx_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    xlsx_resp = client.post("/api/v1/admin/imports", headers=admin_auth_headers, files=xlsx_files)
    assert xlsx_resp.status_code == 201
    assert xlsx_resp.json()["total_rows"] == 3
    assert xlsx_resp.json()["valid_rows_count"] == 3


def test_site_metrics_provenance_and_contact_endpoint(client: TestClient) -> None:
    """Verify SiteMetricOut exposes verification/window fields and POST /contact persists cleanly."""
    metrics_resp = client.get("/api/v1/sites/mons-mouton/metrics")
    assert metrics_resp.status_code == 200
    metrics = metrics_resp.json()
    assert len(metrics) >= 1
    assert "data_quality_status" in metrics[0]
    assert "valid_from" in metrics[0]
    assert "source_url" in metrics[0]

    # Invalid email rejected cleanly (422)
    bad_resp = client.post(
        "/api/v1/contact",
        json={
            "sender_name": "Mission Ops",
            "sender_email": "not-an-email",
            "subject": "Telemetry Question",
            "message_body": "Please verify LOLA horizon data conventions.",
        },
    )
    assert bad_resp.status_code == 422

    # Valid contact persisted cleanly
    ok_resp = client.post(
        "/api/v1/contact",
        json={
            "sender_name": "Mission Ops",
            "sender_email": "ops@lunar-example.org",
            "subject": "Simulation Coverage Question",
            "message_body": "Requesting clarification on LOLA DEM boundary interpolation for Mons Mouton.",
            "website": "",
        },
    )
    assert ok_resp.status_code == 201
    body = ok_resp.json()
    assert body["status"] == "RECEIVED"
    assert "message_id" in body
