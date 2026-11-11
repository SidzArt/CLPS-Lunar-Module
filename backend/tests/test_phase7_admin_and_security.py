"""Phase 7 comprehensive test suite for Admin Portal RBAC, CRUD, Firmware Editor, and Security."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import redact_audit_value
from app.core.config import settings
from app.core.rate_limit import auth_login_rate_limiter
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.admin import Admin, AdminRoleLink, Role
from app.models.catalogue import NASARegion
from app.models.codex import HardwareCodeVersion
from app.models.metrics import ParameterDefinition


def _ensure_role_user(
    *,
    username: str,
    password: str,
    role_keys: list[str],
    display_name: str | None = None,
) -> dict[str, Any]:
    """Create or reset a dedicated test user with specified roles for clean RBAC assertions."""
    session: Session = SessionLocal()
    try:
        user = session.scalar(select(Admin).where(Admin.username == username))
        if user is None:
            user = Admin(
                username=username,
                password_hash=hash_password(password),
                display_name=display_name or username,
                is_active=True,
                password_updated_at=datetime.now(UTC),
            )
            session.add(user)
            session.flush()
        else:
            user.password_hash = hash_password(password)
            user.is_active = True
            user.failed_login_count = 0
            user.locked_until = None
            user.password_must_rotate = False
            session.flush()

        existing_links = list(
            session.scalars(
                select(AdminRoleLink).where(AdminRoleLink.admin_id == user.admin_id)
            ).all()
        )
        for lnk in existing_links:
            session.delete(lnk)
        session.flush()

        for rk in role_keys:
            role = session.scalar(select(Role).where(Role.role_key == rk))
            assert role is not None, f"Role {rk} missing from roles table"
            session.add(AdminRoleLink(admin_id=user.admin_id, role_id=role.role_id))
        session.commit()
        session.refresh(user)
        return {"admin_id": str(user.admin_id), "username": user.username, "password": password}
    finally:
        session.close()


def _bearer_headers(client: TestClient, username: str, password: str) -> dict[str, str]:
    auth_login_rate_limiter.reset()
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["session_token"]
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def reset_auth_limiter() -> Any:
    """Keep login rate limiter state isolated across tests."""
    auth_login_rate_limiter.reset()
    yield
    auth_login_rate_limiter.reset()


def test_security_headers_and_strict_cors_preflight(client: TestClient) -> None:
    """Verify baseline HTTP security headers and explicit CORS allow-headers policy."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert "permissions-policy" in resp.headers
    assert (
        resp.headers.get("content-security-policy") == "default-src 'none'; frame-ancestors 'none'"
    )

    preflight = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, X-CSRF-Token",
        },
    )
    assert preflight.status_code in (200, 204)
    allowed_hdrs = (preflight.headers.get("access-control-allow-headers") or "").lower()
    assert "*" not in allowed_hdrs
    assert "x-csrf-token" in allowed_hdrs


def test_cookie_auth_double_submit_csrf_and_origin_protection(
    client: TestClient,
    admin_auth_headers: dict[str, str],
) -> None:
    """Browser HttpOnly cookie sessions must reject missing/invalid CSRF tokens and foreign Origins."""
    user = _ensure_role_user(
        username="phase7_csrf_editor",
        password="Phase7Strong!User1",
        role_keys=["site_editor"],
    )
    client.cookies.clear()
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": user["username"], "password": user["password"]},
        headers={"Origin": "http://localhost:3000"},
    )
    assert login_resp.status_code == 200
    assert "clps_session" in client.cookies
    assert "clps_csrf" in client.cookies
    csrf_val = client.cookies.get("clps_csrf")
    assert csrf_val == login_resp.json()["csrf_token"]

    # Cookie-authenticated GET /auth/me works cleanly
    me_resp = client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200

    # Unsafe POST via cookie WITHOUT X-CSRF-Token -> 403
    no_csrf_resp = client.post(
        "/api/v1/admin/sources",
        json={"title": "Missing CSRF Source"},
        headers={"Origin": "http://localhost:3000"},
    )
    assert no_csrf_resp.status_code == 403

    # Unsafe POST via cookie WITH wrong X-CSRF-Token -> 403
    bad_csrf_resp = client.post(
        "/api/v1/admin/sources",
        json={"title": "Wrong CSRF Source"},
        headers={"Origin": "http://localhost:3000", "X-CSRF-Token": "forged.token123"},
    )
    assert bad_csrf_resp.status_code == 403

    # Unsafe POST from disallowed foreign Origin even with valid CSRF token -> 403
    bad_origin_resp = client.post(
        "/api/v1/admin/sources",
        json={"title": "Evil Origin Source"},
        headers={"Origin": "https://evil.example.org", "X-CSRF-Token": csrf_val or ""},
    )
    assert bad_origin_resp.status_code == 403

    # Valid Origin + valid matching CSRF token -> 201
    ok_resp = client.post(
        "/api/v1/admin/sources",
        json={"title": "NASA PDS Validated Source", "agency_name": "NASA"},
        headers={"Origin": "http://localhost:3000", "X-CSRF-Token": csrf_val or ""},
    )
    assert ok_resp.status_code == 201
    client.cookies.clear()


def test_login_lockout_unlock_rate_limit_session_rotation_and_change_password(
    client: TestClient,
    admin_auth_headers: dict[str, str],
) -> None:
    """Verify failed-login lockout, super_admin unlock, session rotation, and password change."""
    creds = _ensure_role_user(
        username="phase7_lockout_user",
        password="InitialStrong!Pass12",
        role_keys=["site_editor"],
    )

    # 1. Session fixation rotation: second login revokes old session cookie token
    client.cookies.clear()
    first_login = client.post(
        "/api/v1/auth/login",
        json={"username": creds["username"], "password": creds["password"]},
    )
    assert first_login.status_code == 200
    old_token = first_login.json()["session_token"]

    second_login = client.post(
        "/api/v1/auth/login",
        json={"username": creds["username"], "password": creds["password"]},
    )
    assert second_login.status_code == 200
    new_token = second_login.json()["session_token"]
    assert new_token != old_token

    client.cookies.clear()
    old_probe = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_token}"})
    assert old_probe.status_code == 401

    # 2. Failed login lockout after threshold bad attempts -> 423 Locked
    for _ in range(settings.AUTH_LOCKOUT_THRESHOLD):
        bad = client.post(
            "/api/v1/auth/login",
            json={"username": creds["username"], "password": "DefinitelyWrongPassword!99"},
        )
        assert bad.status_code == 401

    locked_resp = client.post(
        "/api/v1/auth/login",
        json={"username": creds["username"], "password": creds["password"]},
    )
    assert locked_resp.status_code == 423

    # 3. Super-admin unlocks account cleanly
    unlock_resp = client.patch(
        f"/api/v1/admin/users/{creds['admin_id']}",
        headers=admin_auth_headers,
        json={"unlock_account": True},
    )
    assert unlock_resp.status_code == 200
    assert unlock_resp.json()["failed_login_count"] == 0
    assert unlock_resp.json()["locked_until"] is None

    # 4. Change password rejects weak password & rotates sessions on success
    relogin = client.post(
        "/api/v1/auth/login",
        json={"username": creds["username"], "password": creds["password"]},
    )
    assert relogin.status_code == 200
    active_tok = relogin.json()["session_token"]
    client.cookies.clear()

    weak_pw = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {active_tok}"},
        json={"current_password": creds["password"], "new_password": "short"},
    )
    assert weak_pw.status_code == 422

    change_ok = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {active_tok}"},
        json={"current_password": creds["password"], "new_password": "RotatedStrong!Pass34"},
    )
    assert change_ok.status_code == 200
    rotated_tok = change_ok.json()["session_token"]
    assert rotated_tok != active_tok

    # Old token immediately invalid
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {active_tok}"}).status_code
        == 401
    )
    # New token valid
    assert (
        client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {rotated_tok}"}
        ).status_code
        == 200
    )

    # 5. Auth login rate limiter triggers 429 on excessive burst from same host
    for _ in range(settings.AUTH_RATE_LIMIT_MAX_ATTEMPTS):
        client.post(
            "/api/v1/auth/login",
            json={"username": "nonexistent_burst_user", "password": "BadPassword!123"},
        )
    burst_resp = client.post(
        "/api/v1/auth/login",
        json={"username": "nonexistent_burst_user", "password": "BadPassword!123"},
    )
    assert burst_resp.status_code == 429


def test_rbac_role_matrix_401_and_403_boundaries(
    client: TestClient,
    admin_auth_headers: dict[str, str],
    viewer_auth_headers: dict[str, str],
) -> None:
    """Verify strict 401 vs 403 separation across super/system/editor/research/hardware/viewer."""
    client.cookies.clear()
    # Unauthenticated -> 401 across admin endpoints
    for path in (
        "/api/v1/admin/overview",
        "/api/v1/admin/users",
        "/api/v1/admin/audit-logs",
        "/api/v1/admin/system/health",
        "/api/v1/admin/sites",
        "/api/v1/admin/codex/devices",
        "/api/v1/admin/hardware/variables",
    ):
        assert client.get(path).status_code == 401, f"Expected 401 for unauthenticated {path}"

    sys_user = _ensure_role_user(
        username="phase7_sys_admin",
        password="SystemStrong!Pass12",
        role_keys=["system_admin"],
    )
    hw_user = _ensure_role_user(
        username="phase7_hw_admin",
        password="HardwareStrong!Pass12",
        role_keys=["hardware_admin"],
    )
    res_user = _ensure_role_user(
        username="phase7_res_admin",
        password="ResearchStrong!Pass12",
        role_keys=["research_admin"],
    )

    sys_headers = _bearer_headers(client, sys_user["username"], sys_user["password"])
    hw_headers = _bearer_headers(client, hw_user["username"], hw_user["password"])
    res_headers = _bearer_headers(client, res_user["username"], res_user["password"])

    # viewer -> overview & diagnostics allowed; audit/users/mutations forbidden
    assert client.get("/api/v1/admin/overview", headers=viewer_auth_headers).status_code == 200
    assert (
        client.get("/api/v1/admin/simulations/diagnostics", headers=viewer_auth_headers).status_code
        == 200
    )
    assert client.get("/api/v1/admin/users", headers=viewer_auth_headers).status_code == 403
    assert client.get("/api/v1/admin/audit-logs", headers=viewer_auth_headers).status_code == 403
    assert (
        client.post(
            "/api/v1/admin/sources",
            headers=viewer_auth_headers,
            json={"title": "Blocked"},
        ).status_code
        == 403
    )

    # system_admin -> audit & health & hardware read allowed; /admin/users strictly super_admin!
    assert client.get("/api/v1/admin/audit-logs", headers=sys_headers).status_code == 200
    assert client.get("/api/v1/admin/system/health", headers=sys_headers).status_code == 200
    assert client.get("/api/v1/admin/users", headers=sys_headers).status_code == 403

    # hardware_admin -> codex & simulations diagnostics & hardware variables allowed; users/audit denied
    assert client.get("/api/v1/admin/codex/devices", headers=hw_headers).status_code == 200
    assert client.get("/api/v1/admin/hardware/variables", headers=hw_headers).status_code == 200
    assert (
        client.get("/api/v1/admin/simulations/diagnostics", headers=hw_headers).status_code == 200
    )
    assert client.get("/api/v1/admin/users", headers=hw_headers).status_code == 403
    assert client.get("/api/v1/admin/audit-logs", headers=hw_headers).status_code == 403

    # research_admin -> imports & sources allowed; hardware/users denied
    assert client.get("/api/v1/admin/imports", headers=res_headers).status_code == 200
    assert client.get("/api/v1/admin/sources", headers=res_headers).status_code == 200
    assert client.get("/api/v1/admin/codex/devices", headers=res_headers).status_code == 403
    assert client.get("/api/v1/admin/users", headers=res_headers).status_code == 403


def test_user_management_lifecycle_and_safety_guards(
    client: TestClient,
    admin_auth_headers: dict[str, str],
) -> None:
    """Test super_admin user creation, policy check, self-lockout block, role revocation, reset."""
    roles_resp = client.get("/api/v1/admin/roles", headers=admin_auth_headers)
    assert roles_resp.status_code == 200
    role_keys = {r["role_key"] for r in roles_resp.json()}
    assert {
        "super_admin",
        "system_admin",
        "site_editor",
        "research_admin",
        "hardware_admin",
        "viewer",
    } <= role_keys

    # Password policy enforcement
    bad_user = client.post(
        "/api/v1/admin/users",
        headers=admin_auth_headers,
        json={
            "username": "weak_pw_user",
            "password": "too_weak_no_digits!",
            "role_keys": ["viewer"],
        },
    )
    assert bad_user.status_code == 422

    # Create valid user & inspect listing never exposes password_hash
    create_resp = client.post(
        "/api/v1/admin/users",
        headers=admin_auth_headers,
        json={
            "username": "phase7_managed_op",
            "password": "ManagedStrong!Pass99",
            "display_name": "Managed Operator",
            "role_keys": ["viewer"],
        },
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert "password_hash" not in created
    target_id = created["admin_id"]

    # Login as new user to create an active session
    op_headers = _bearer_headers(client, "phase7_managed_op", "ManagedStrong!Pass99")
    assert client.get("/api/v1/admin/overview", headers=op_headers).status_code == 200

    # Reassigning role revokes active sessions of target user
    reassign_resp = client.patch(
        f"/api/v1/admin/users/{target_id}",
        headers=admin_auth_headers,
        json={"role_keys": ["site_editor"]},
    )
    assert reassign_resp.status_code == 200
    assert reassign_resp.json()["roles"] == ["site_editor"]
    assert client.get("/api/v1/auth/me", headers=op_headers).status_code == 401

    # Self-deactivation guard for test_super_admin
    me_id = client.get("/api/v1/auth/me", headers=admin_auth_headers).json()["admin_id"]
    self_disable = client.patch(
        f"/api/v1/admin/users/{me_id}",
        headers=admin_auth_headers,
        json={"is_active": False},
    )
    assert self_disable.status_code == 400
    self_demote = client.patch(
        f"/api/v1/admin/users/{me_id}",
        headers=admin_auth_headers,
        json={"role_keys": ["viewer"]},
    )
    assert self_demote.status_code == 400

    # Password reset & manual session revoke
    reset_resp = client.post(
        f"/api/v1/admin/users/{target_id}/reset-password",
        headers=admin_auth_headers,
        json={"new_password": "ResetStrong!Pass77", "password_must_rotate": True},
    )
    assert reset_resp.status_code == 200
    assert reset_resp.json()["password_must_rotate"] is True

    new_op_headers = _bearer_headers(client, "phase7_managed_op", "ResetStrong!Pass77")
    revoke_resp = client.post(
        f"/api/v1/admin/users/{target_id}/revoke-sessions",
        headers=admin_auth_headers,
    )
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["revoked_sessions_count"] >= 1
    assert client.get("/api/v1/auth/me", headers=new_op_headers).status_code == 401


def test_site_crud_sections_proscons_history_metrics_media_archive_delete(
    client: TestClient,
    admin_auth_headers: dict[str, str],
) -> None:
    """Exercise full admin site editorial lifecycle, provenance enforcement, and orphan media scan."""
    # Ensure a region and parameter exist
    session: Session = SessionLocal()
    try:
        region = session.scalar(select(NASARegion))
        if not region:
            region = NASARegion(region_code="PHASE7-REG", region_name="Phase 7 South Polar")
            session.add(region)
            session.flush()
        param = session.scalar(select(ParameterDefinition))
        if not param:
            param = ParameterDefinition(
                parameter_key="phase7_slope_deg",
                display_name="Phase 7 Slope",
                unit="deg",
                value_type="numeric",
                comparison_direction="lower",
                validation_min=0.0,
                validation_max=90.0,
            )
            session.add(param)
            session.flush()
        session.commit()
        region_id = region.region_id
        param_id = param.parameter_id
    finally:
        session.close()

    # Create source for verified metric provenance check
    src_resp = client.post(
        "/api/v1/admin/sources",
        headers=admin_auth_headers,
        json={"title": "LRO LOLA Slope Atlas 2026", "agency_name": "NASA GSFC"},
    )
    assert src_resp.status_code == 201
    source_id = src_resp.json()["source_id"]

    # Patch source
    patch_src = client.patch(
        f"/api/v1/admin/sources/{source_id}",
        headers=admin_auth_headers,
        json={"dataset_version": "v2.1"},
    )
    assert patch_src.status_code == 200
    assert patch_src.json()["dataset_version"] == "v2.1"

    # List regions & parameters
    assert client.get("/api/v1/admin/regions", headers=admin_auth_headers).status_code == 200
    assert client.get("/api/v1/admin/parameters", headers=admin_auth_headers).status_code == 200

    # Create draft site
    site_resp = client.post(
        "/api/v1/admin/sites",
        headers=admin_auth_headers,
        json={
            "site_code": "PHASE7_SITE_ALPHA",
            "site_name": "Phase 7 Alpha Crater",
            "region_id": region_id,
            "latitude_deg": -84.2,
            "longitude_deg": 28.5,
            "elevation_m": 1240.0,
            "catalogue_status": "draft",
        },
    )
    assert site_resp.status_code == 201
    site_id = site_resp.json()["site_id"]

    # Admin list & detail include draft
    list_resp = client.get(
        "/api/v1/admin/sites?catalogue_status=draft&search=PHASE7_SITE_ALPHA",
        headers=admin_auth_headers,
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] >= 1
    assert (
        client.get(f"/api/v1/admin/sites/{site_id}", headers=admin_auth_headers).status_code == 200
    )

    # Section CRUD
    sec = client.post(
        f"/api/v1/admin/sites/{site_id}/sections",
        headers=admin_auth_headers,
        json={"section_key": "geology", "title": "Basalt Regolith", "body": "Initial notes."},
    )
    assert sec.status_code == 201
    content_id = sec.json()["content_id"]
    assert (
        client.patch(
            f"/api/v1/admin/sites/{site_id}/sections/{content_id}",
            headers=admin_auth_headers,
            json={"body": "Updated petrologic synthesis."},
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/admin/sites/{site_id}/sections", headers=admin_auth_headers
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"/api/v1/admin/sites/{site_id}/sections/{content_id}",
            headers=admin_auth_headers,
        ).status_code
        == 200
    )

    # Pro/Con CRUD
    pc = client.post(
        f"/api/v1/admin/sites/{site_id}/pros-cons",
        headers=admin_auth_headers,
        json={"point_type": "PRO", "title": "Illumination", "body": "High ridge exposure."},
    )
    assert pc.status_code == 201
    point_id = pc.json()["point_id"]
    assert (
        client.patch(
            f"/api/v1/admin/sites/{site_id}/pros-cons/{point_id}",
            headers=admin_auth_headers,
            json={"confidence": 0.92},
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"/api/v1/admin/sites/{site_id}/pros-cons/{point_id}",
            headers=admin_auth_headers,
        ).status_code
        == 200
    )

    # History CRUD
    hist = client.post(
        f"/api/v1/admin/sites/{site_id}/history",
        headers=admin_auth_headers,
        json={
            "event_date": "2024-02-22",
            "title": "Reconnaissance Target",
            "description": "Selected for south polar thermal mapping.",
            "source_id": source_id,
        },
    )
    assert hist.status_code == 201
    history_id = hist.json()["history_id"]
    assert (
        client.patch(
            f"/api/v1/admin/sites/{site_id}/history/{history_id}",
            headers=admin_auth_headers,
            json={"title": "Updated Reconnaissance Milestone"},
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"/api/v1/admin/sites/{site_id}/history/{history_id}",
            headers=admin_auth_headers,
        ).status_code
        == 200
    )

    # Metrics provenance enforcement: verified without source_id rejected -> 422
    bad_metric = client.put(
        f"/api/v1/admin/sites/{site_id}/metrics",
        headers=admin_auth_headers,
        json={
            "metrics": [
                {
                    "parameter_id": param_id,
                    "numeric_value": 4.2,
                    "data_quality_status": "verified",
                }
            ]
        },
    )
    assert bad_metric.status_code == 422

    # Valid verified metric with explicit source_id succeeds
    ok_metric = client.put(
        f"/api/v1/admin/sites/{site_id}/metrics",
        headers=admin_auth_headers,
        json={
            "metrics": [
                {
                    "parameter_id": param_id,
                    "numeric_value": 4.2,
                    "source_id": source_id,
                    "data_quality_status": "verified",
                }
            ]
        },
    )
    assert ok_metric.status_code == 200
    assert ok_metric.json()[0]["source_id"] == source_id

    # Orphan file detection under MEDIA_ROOT
    orphan_file = Path(settings.MEDIA_ROOT) / "phase7_orphan_test.webp"
    Path(settings.MEDIA_ROOT).mkdir(parents=True, exist_ok=True)
    orphan_file.write_bytes(b"orphan-test")
    try:
        media_list = client.get("/api/v1/admin/media", headers=admin_auth_headers)
        assert media_list.status_code == 200
        orphan_paths = {o["relative_path"] for o in media_list.json()["orphan_files"]}
        assert "media/phase7_orphan_test.webp" in orphan_paths
    finally:
        orphan_file.unlink(missing_ok=True)

    # Publish -> cannot delete while published (409) -> archive -> delete
    assert (
        client.patch(
            f"/api/v1/admin/sites/{site_id}",
            headers=admin_auth_headers,
            json={"catalogue_status": "published"},
        ).status_code
        == 200
    )
    assert (
        client.delete(f"/api/v1/admin/sites/{site_id}", headers=admin_auth_headers).status_code
        == 409
    )
    arch = client.post(f"/api/v1/admin/sites/{site_id}/archive", headers=admin_auth_headers)
    assert arch.status_code == 200
    assert arch.json()["catalogue_status"] == "archived"
    assert (
        client.delete(f"/api/v1/admin/sites/{site_id}", headers=admin_auth_headers).status_code
        == 200
    )


def test_firmware_editor_detail_diff_activate_validate_and_variables(
    client: TestClient,
    admin_auth_headers: dict[str, str],
) -> None:
    """Verify full Split-Pane Firmware Editor API contracts and live Variable Reference."""
    base_src = (
        "// CODEX Motion v1\n"
        '#error "SAFETY BLOCK: Verify stepper pinouts"\n'
        "const int STEP_RATE = {{NEMA17_MAX_STEP_RATE}};\n"
        "void setup() {}\n"
        "void loop() {}\n"
    )
    v2_src = (
        "// CODEX Motion v2\n"
        '#error "SAFETY BLOCK: Verify stepper pinouts"\n'
        "const int STEP_RATE = {{NEMA17_MAX_STEP_RATE}};\n"
        "const int ACCEL = {{NEMA17_ACCEL}};\n"
        "void setup() {}\n"
        "void loop() {}\n"
    )

    ph_rate = {
        "placeholder_key": "NEMA17_MAX_STEP_RATE",
        "description": "Safe maximum NEMA17 step rate",
        "data_type": "int",
        "unit": "steps/s",
        "required": True,
        "default_value": 1200,
    }
    ph_accel = {
        "placeholder_key": "NEMA17_ACCEL",
        "description": "Acceleration limit",
        "data_type": "int",
        "unit": "steps/s^2",
        "required": True,
        "default_value": 400,
    }

    r1 = client.post(
        "/api/v1/admin/hardware/code-versions",
        headers=admin_auth_headers,
        json={
            "controller_key": "motion_uno",
            "version_label": "v7-ed-1",
            "source_code": base_src,
            "board_target": "arduino:avr:uno",
            "placeholders": [ph_rate],
            "activate": True,
        },
    )
    assert r1.status_code == 201
    v1_id = r1.json()["code_version_id"]

    # Duplicate version label -> 409 Conflict
    dup_resp = client.post(
        "/api/v1/admin/hardware/code-versions",
        headers=admin_auth_headers,
        json={
            "controller_key": "motion_uno",
            "version_label": "v7-ed-1",
            "source_code": base_src,
            "board_target": "arduino:avr:uno",
            "placeholders": [ph_rate],
            "activate": False,
        },
    )
    assert dup_resp.status_code == 409

    # Malformed placeholder token rejected -> 400
    bad_tok = client.post(
        "/api/v1/admin/hardware/code-versions",
        headers=admin_auth_headers,
        json={
            "controller_key": "motion_uno",
            "version_label": "v7-ed-bad",
            "source_code": "const int X = {{bad key}}; void setup(){} void loop(){}",
            "board_target": "arduino:avr:uno",
            "placeholders": [],
            "activate": False,
        },
    )
    assert bad_tok.status_code == 400

    r2 = client.post(
        "/api/v1/admin/hardware/code-versions",
        headers=admin_auth_headers,
        json={
            "controller_key": "motion_uno",
            "version_label": "v7-ed-2",
            "source_code": v2_src,
            "board_target": "arduino:avr:uno",
            "placeholders": [ph_rate, ph_accel],
            "activate": False,
        },
    )
    assert r2.status_code == 201
    v2_id = r2.json()["code_version_id"]

    # Detail GET includes full source_code
    det = client.get(
        f"/api/v1/admin/hardware/code-versions/{v2_id}",
        headers=admin_auth_headers,
    )
    assert det.status_code == 200
    assert det.json()["source_code"] == v2_src
    assert det.json()["is_active"] is False

    # Activate v2 -> audits and swaps active flag without flashing
    act = client.post(
        f"/api/v1/admin/hardware/code-versions/{v2_id}/activate",
        headers=admin_auth_headers,
    )
    assert act.status_code == 200
    assert act.json()["is_active"] is True
    v1_after = client.get(
        f"/api/v1/admin/hardware/code-versions/{v1_id}",
        headers=admin_auth_headers,
    )
    assert v1_after.json()["is_active"] is False

    # Unified diff between v1 and v2
    diff = client.get(
        f"/api/v1/admin/hardware/code-versions/{v1_id}/diff/{v2_id}",
        headers=admin_auth_headers,
    )
    assert diff.status_code == 200
    diff_data = diff.json()
    assert diff_data["added_lines"] >= 1
    assert "+const int ACCEL = {{NEMA17_ACCEL}};" in diff_data["unified_diff"]
    assert any(
        c["key"] == "NEMA17_ACCEL" and c["change"] == "added"
        for c in diff_data["placeholder_changes"]
    )

    # Live backend-driven Variable Reference catalog
    vars_resp = client.get("/api/v1/admin/hardware/variables", headers=admin_auth_headers)
    assert vars_resp.status_code == 200
    var_keys = {v["key"] for v in vars_resp.json()}
    assert "NEMA17_STEPS_PER_REV" in var_keys
    assert "MOON_LED_VERIFIED_REGIONS" in var_keys
    assert "NEMA17_ACCEL" in var_keys

    # Admin configs & runs listing endpoints
    assert (
        client.get("/api/v1/admin/codex/configurations", headers=admin_auth_headers).status_code
        == 200
    )
    assert client.get("/api/v1/admin/codex/runs", headers=admin_auth_headers).status_code == 200

    # Clean up temporary code versions
    cleanup_db: Session = SessionLocal()
    try:
        for vid in (v1_id, v2_id):
            row = cleanup_db.get(HardwareCodeVersion, vid)
            if row is not None:
                cleanup_db.delete(row)
        cleanup_db.commit()
    finally:
        cleanup_db.close()


def test_audit_log_redaction_and_system_health_no_host_paths(
    client: TestClient,
    admin_auth_headers: dict[str, str],
) -> None:
    """Verify audit snapshot secret redaction and live system health probes omit OS paths."""
    redacted = redact_audit_value(
        {
            "password": "secret123",
            "nested": {"psk_hex": "deadbeef", "safe_flag": True},
        }
    )
    assert redacted["password"] == "[REDACTED]"
    assert redacted["nested"]["psk_hex"] == "[REDACTED]"
    assert redacted["nested"]["safe_flag"] is True

    # Trigger health check & confirm real telemetry without filesystem paths
    health_resp = client.get("/api/v1/admin/system/health", headers=admin_auth_headers)
    assert health_resp.status_code == 200
    health_data = health_resp.json()
    comp_keys = {c["component_key"] for c in health_data["components"]}
    assert {
        "postgresql",
        "spice_ephemeris",
        "lola_dem_rasters",
        "ollama_llm",
        "simulation_worker",
        "codex_hardware",
    } <= comp_keys
    serialized_health = str(health_data)
    assert "/Users/" not in serialized_health
    assert "backend/app" not in serialized_health

    # Audit log list returns entries with sensitive values redacted
    audit_resp = client.get(
        "/api/v1/admin/audit-logs?page=1&page_size=20", headers=admin_auth_headers
    )
    assert audit_resp.status_code == 200
    assert audit_resp.json()["total"] >= 1
