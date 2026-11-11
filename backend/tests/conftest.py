"""Pytest test configuration and isolated test database/storage fixtures."""

import os
import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

# Configure isolated *_test database and temporary storage BEFORE importing app.* modules.
_DEFAULT_TEST_DB_URL = (
    "postgresql+psycopg://clps_app:clps_dev_pass_2026@localhost:5432/clps_luna_test"
)
_RESOLVED_TEST_DB_URL = os.environ.get("CLPS_TEST_DATABASE_URL") or _DEFAULT_TEST_DB_URL
_PARSED_DB_NAME = urlparse(_RESOLVED_TEST_DB_URL).path.lstrip("/")
if not _PARSED_DB_NAME.endswith("_test"):
    raise RuntimeError(
        f"Refusing to run tests against non-test database '{_PARSED_DB_NAME}'. "
        "Target database name must end with '_test'."
    )

_TEST_STORAGE_DIR = Path(tempfile.mkdtemp(prefix="clps_luna_test_storage_"))
_TEST_MEDIA_DIR = _TEST_STORAGE_DIR / "media"
_TEST_IMPORTS_DIR = _TEST_STORAGE_DIR / "imports"
_TEST_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
_TEST_IMPORTS_DIR.mkdir(parents=True, exist_ok=True)

os.environ["DATABASE_URL"] = _RESOLVED_TEST_DB_URL
os.environ["MEDIA_ROOT"] = str(_TEST_MEDIA_DIR)
os.environ["IMPORT_STAGING_ROOT"] = str(_TEST_IMPORTS_DIR)

from alembic.config import Config as AlembicConfig
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command as alembic_command
from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.admin import Admin, AdminRoleLink, Role


@pytest.fixture(scope="session", autouse=True)
def prepare_isolated_test_environment() -> Generator[None, None, None]:
    """Reset the dedicated *_test schema, run Alembic migrations, and clean temp storage."""
    db_name = urlparse(str(engine.url)).path.lstrip("/")
    if not db_name.endswith("_test"):
        raise RuntimeError(f"Unsafe test engine target database '{db_name}'")

    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))

    backend_dir = Path(__file__).resolve().parents[1]
    alembic_cfg = AlembicConfig(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", _RESOLVED_TEST_DB_URL)
    alembic_command.upgrade(alembic_cfg, "head")

    try:
        yield
    finally:
        engine.dispose()
        shutil.rmtree(_TEST_STORAGE_DIR, ignore_errors=True)


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    """Test client for FastAPI HTTP requests."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Database session fixture with automatic transaction rollback after each test."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="session")
def admin_account() -> dict[str, Any]:
    """Ensure a super admin account exists with all administrative roles."""
    session = SessionLocal()
    admin = session.query(Admin).filter_by(username="test_super_admin").first()
    if not admin:
        admin = Admin(
            username="test_super_admin",
            password_hash=hash_password("TestAdminPass123!"),
            display_name="Test Super Admin",
            is_active=True,
        )
        session.add(admin)
        session.commit()
        session.refresh(admin)

        roles = session.query(Role).all()
        for r in roles:
            link = AdminRoleLink(admin_id=admin.admin_id, role_id=r.role_id)
            session.add(link)
        session.commit()

    admin_data = {
        "username": "test_super_admin",
        "password": "TestAdminPass123!",
        "admin_id": str(admin.admin_id),
    }
    session.close()
    return admin_data


@pytest.fixture(scope="session")
def admin_auth_headers(client: TestClient, admin_account: dict[str, Any]) -> dict[str, str]:
    """Log in as super admin and return Authorization Bearer header without leaking cookies."""
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": admin_account["username"], "password": admin_account["password"]},
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    token = login_resp.json()["session_token"]
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def viewer_account() -> dict[str, Any]:
    """Ensure a restricted admin account exists with only viewer permissions."""
    session = SessionLocal()
    admin = session.query(Admin).filter_by(username="test_viewer").first()
    if not admin:
        admin = Admin(
            username="test_viewer",
            password_hash=hash_password("ViewerPass123!"),
            display_name="Test Viewer",
            is_active=True,
        )
        session.add(admin)
        session.commit()
        session.refresh(admin)

        viewer_role = session.query(Role).filter_by(role_key="viewer").first()
        if viewer_role:
            link = AdminRoleLink(admin_id=admin.admin_id, role_id=viewer_role.role_id)
            session.add(link)
            session.commit()

    viewer_data = {
        "username": "test_viewer",
        "password": "ViewerPass123!",
        "admin_id": str(admin.admin_id),
    }
    session.close()
    return viewer_data


@pytest.fixture(scope="session")
def viewer_auth_headers(client: TestClient, viewer_account: dict[str, Any]) -> dict[str, str]:
    """Log in as restricted viewer and return Authorization Bearer header without leaking cookies."""
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": viewer_account["username"], "password": viewer_account["password"]},
    )
    assert login_resp.status_code == 200, f"Viewer login failed: {login_resp.text}"
    token = login_resp.json()["session_token"]
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}
