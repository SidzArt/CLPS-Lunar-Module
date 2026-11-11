"""Database contract verification tests for CLPS Luna Browser Phase 1."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.admin import Admin, AdminSession
from app.models.catalogue import (
    LandingSite,
    NASARegion,
    SiteContent,
    SiteProCon,
)
from app.models.codex import MoonLedRegion, MotorCalibrationProfile
from app.models.operations import BackgroundJob


def test_health_endpoints(client: TestClient) -> None:
    """Verify that liveness and readiness diagnostic endpoints respond with 200 OK."""
    # Test Liveness
    health_resp = client.get("/api/v1/health")
    assert health_resp.status_code == 200
    health_data = health_resp.json()
    assert health_data["status"] == "SYSTEM_OK"
    assert "timestamp_utc" in health_data

    # Test Readiness (probes active PostgreSQL connection)
    ready_resp = client.get("/api/v1/ready")
    assert ready_resp.status_code == 200
    ready_data = ready_resp.json()
    assert ready_data["status"] == "READY"
    assert ready_data["database"] is True
    assert ready_data["database_latency_ms"] >= 0.0

    # Test root convenience routes
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200


def test_request_id_and_security_headers(client: TestClient) -> None:
    """Verify that middleware injects X-Request-ID, timing, and security headers."""
    resp = client.get("/api/v1/health")
    assert "X-Request-ID" in resp.headers
    assert resp.headers["X-Request-ID"].startswith("req_")
    assert "X-Process-Time" in resp.headers
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


def test_uncapped_text_storage_in_site_content(db_session: Session) -> None:
    """Verify requirement REQ-DB-02: PostgreSQL TEXT stores 10,000+ words without truncation."""
    # Create test region and site
    region = NASARegion(
        region_code="TEST_SOUTH_POLE",
        region_name="Test Lunar South Pole Region",
        source_status="official",
    )
    db_session.add(region)
    db_session.flush()

    site = LandingSite(
        region_id=region.region_id,
        site_code="TEST-SITE-001",
        site_slug="test-site-001",
        site_name="Test Malapert Candidate Point",
        latitude_deg=-84.9000000,
        longitude_deg=12.9000000,
        catalogue_status="draft",
    )
    db_session.add(site)
    db_session.flush()

    # Generate an extensive 13,500-word research text (9 words * 1500 repetitions)
    word_block = "lunar regolith illumination permanent shadow volatile ice topography elevation "
    repetitions = 1500  # 9 words * 1500 = 13,500 words
    full_research_body = (word_block * repetitions).strip()
    assert len(full_research_body.split()) == 13500

    content = SiteContent(
        site_id=site.site_id,
        section_key="geology",
        title="Comprehensive Lunar Geological Assessment",
        body=full_research_body,
        display_order=1,
    )
    db_session.add(content)
    db_session.flush()

    # Query back and assert exact identity without truncation
    retrieved = db_session.get(SiteContent, content.content_id)
    assert retrieved is not None
    assert retrieved.body == full_research_body
    assert len(retrieved.body.split()) == 13500


def test_coordinate_check_constraints(db_session: Session) -> None:
    """Verify that latitude and longitude check constraints prevent out-of-range coordinates."""
    # Valid site
    site = LandingSite(
        site_code="TEST-VALID-COORDS",
        site_slug="test-valid-coords",
        site_name="Valid Site",
        latitude_deg=0.0,
        longitude_deg=0.0,
    )
    db_session.add(site)
    db_session.flush()

    # Invalid latitude > 90
    invalid_lat_site = LandingSite(
        site_code="TEST-INVALID-LAT",
        site_slug="test-invalid-lat",
        site_name="Invalid Lat Site",
        latitude_deg=95.1234567,  # Out of range!
        longitude_deg=0.0,
    )
    db_session.add(invalid_lat_site)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    # Invalid longitude < -180
    invalid_lon_site = LandingSite(
        site_code="TEST-INVALID-LON",
        site_slug="test-invalid-lon",
        site_name="Invalid Lon Site",
        latitude_deg=-80.0,
        longitude_deg=-185.0,  # Out of range!
    )
    db_session.add(invalid_lon_site)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_site_pros_cons_constraint(db_session: Session) -> None:
    """Verify that site_pros_cons strictly requires point_type to be PRO or CON."""
    site = LandingSite(
        site_code="TEST-SITE-PROCON",
        site_slug="test-site-procon",
        site_name="Test Pro Con Site",
        latitude_deg=-85.0,
        longitude_deg=20.0,
    )
    db_session.add(site)
    db_session.flush()

    # Valid PRO
    pro_point = SiteProCon(
        site_id=site.site_id,
        point_type="PRO",
        title="Direct Line of Sight to Earth",
        body="Offers 88% direct visibility throughout synodic cycle.",
    )
    db_session.add(pro_point)
    db_session.flush()
    assert pro_point.point_id is not None

    # Invalid point_type ('NEUTRAL')
    invalid_point = SiteProCon(
        site_id=site.site_id,
        point_type="NEU",  # Not PRO or CON
        title="Invalid Point",
        body="This should trigger check constraint failure.",
    )
    db_session.add(invalid_point)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_site_slug_uniqueness(db_session: Session) -> None:
    """Verify that site_slug is unique across the landing_sites table."""
    site1 = LandingSite(
        site_code="SITE-ALPHA",
        site_slug="shared-slug",
        site_name="First Site",
        latitude_deg=-80.0,
        longitude_deg=10.0,
    )
    db_session.add(site1)
    db_session.flush()

    site2 = LandingSite(
        site_code="SITE-BETA",
        site_slug="shared-slug",  # Duplicate slug!
        site_name="Second Site",
        latitude_deg=-81.0,
        longitude_deg=11.0,
    )
    db_session.add(site2)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_admin_session_lifecycle(db_session: Session) -> None:
    """Verify admin password hashing and revocable server-side session contract."""
    admin = Admin(
        username="lead_operator",
        password_hash=hash_password("SuperSecurePassword2026!"),
        display_name="Lead Mission Operator",
        is_active=True,
    )
    db_session.add(admin)
    db_session.flush()

    session = AdminSession(
        admin_id=admin.admin_id,
        token_hash="a1b2c3d4e5f67890" * 4,  # 64-char sha256 hash
        is_revoked=False,
        expires_at=datetime.now(UTC),
    )
    db_session.add(session)
    db_session.flush()

    assert session.session_id is not None
    assert session.is_revoked is False

    # Revoke session
    session.is_revoked = True
    db_session.flush()
    assert db_session.get(AdminSession, session.session_id).is_revoked is True


def test_background_jobs_queue_contract(db_session: Session) -> None:
    """Verify durable job queue table supports JSONB payloads and status states."""
    job = BackgroundJob(
        job_type="SIMULATION",
        payload={
            "site_id": 1,
            "start_time_utc": "2026-04-09T00:00:00Z",
            "duration_days": 30,
        },
        priority=100,
        status="QUEUED",
    )
    db_session.add(job)
    db_session.flush()

    assert job.job_id is not None
    assert job.status == "QUEUED"
    assert job.payload["duration_days"] == 30


def test_moon_led_13_region_contract(db_session: Session) -> None:
    """Verify moon_led_regions table enforces region_index between 1 and 13."""
    valid_region = MoonLedRegion(
        region_index=7,
        region_name="South Pole Rim Sector",
        centroid_lat=-89.5,
        centroid_lon=0.0,
        pixel_indices=[30, 31, 32, 33, 34],
        mapping_version="v1.0",
        is_active=True,
    )
    db_session.add(valid_region)
    db_session.flush()
    assert valid_region.region_id is not None

    # Invalid region_index (14 > 13)
    invalid_region = MoonLedRegion(
        region_index=14,
        region_name="Invalid Sector",
        centroid_lat=0.0,
        centroid_lon=0.0,
        pixel_indices=[1, 2],
    )
    db_session.add(invalid_region)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_motor_calibration_profile_contract(db_session: Session) -> None:
    """Verify motor_calibration_profiles accurately stores kinematic coefficients."""
    calibration = MotorCalibrationProfile(
        controller_key="motion_uno",
        motor_name="NEMA17_SUN_ORBIT",
        gear_reduction_ratio=5.18,
        full_steps_per_rev=200,
        microsteps=16,
        max_step_rate=2500,
        acceleration=800,
        zero_offset_deg=14.2,
        is_active=True,
    )
    db_session.add(calibration)
    db_session.flush()

    assert calibration.calibration_id is not None
    assert calibration.gear_reduction_ratio == 5.18
    assert calibration.max_step_rate == 2500
