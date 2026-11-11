"""FastAPI dependencies for administrator authentication, sessions, CSRF, and RBAC."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.csrf import enforce_csrf_for_cookie_request
from app.core.security import hash_token
from app.db.session import get_db
from app.models.admin import Admin, AdminRoleLink, AdminSession, Role


def get_current_admin(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    clps_session: Annotated[str | None, Cookie()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> Admin:
    """Validate revocable server-side admin session from Bearer token or HttpOnly cookie.

    Browser cookie sessions automatically enforce HMAC-bound double-submit CSRF verification
    and Origin/Referer checks on state-changing requests.
    """
    raw_token: str | None = None
    auth_method: str = "cookie"

    if authorization and authorization.startswith("Bearer "):
        candidate = authorization.split(" ", 1)[1].strip()
        if candidate:
            raw_token = candidate
            auth_method = "bearer"

    if not raw_token and clps_session:
        raw_token = clps_session
        auth_method = "cookie"

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Missing session cookie or Bearer token.",
        )

    if auth_method == "cookie":
        enforce_csrf_for_cookie_request(request, raw_token)

    token_hash = hash_token(raw_token)
    stmt = select(AdminSession).where(AdminSession.token_hash == token_hash)
    session_record = db.scalar(stmt)

    if not session_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token.",
        )

    if session_record.is_revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked.",
        )

    if session_record.expires_at <= datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session token has expired.",
        )

    # Fetch admin with roles
    admin = db.get(Admin, session_record.admin_id)
    if not admin or not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator account is inactive or disabled.",
        )

    # Throttle last_active_at updates (at most once per 60s) to avoid write-on-read overhead
    now = datetime.now(UTC)
    last_active = session_record.last_active_at
    if last_active is not None and last_active.tzinfo is None:
        last_active = last_active.replace(tzinfo=UTC)
    if last_active is None or (now - last_active).total_seconds() >= 60:
        session_record.last_active_at = now
        db.commit()

    request.state.auth_method = auth_method
    request.state.session_id = str(session_record.session_id)
    request.state.raw_session_token = raw_token

    return admin


def get_admin_roles(db: Session, admin_id: str) -> list[str]:
    """Retrieve string role keys for an administrator."""
    stmt = (
        select(Role.role_key)
        .join(AdminRoleLink, Role.role_id == AdminRoleLink.role_id)
        .where(AdminRoleLink.admin_id == admin_id)
    )
    return list(db.scalars(stmt).all())


class RequireRole:
    """Dependency callable checking that the active admin possesses required permissions."""

    def __init__(self, *allowed_roles: str):
        self.allowed_roles = set(allowed_roles)

    def __call__(
        self,
        admin: Annotated[Admin, Depends(get_current_admin)],
        db: Annotated[Session, Depends(get_db)],
    ) -> Admin:
        roles = set(get_admin_roles(db, str(admin.admin_id)))
        # super_admin has universal access
        if "super_admin" in roles or any(r in self.allowed_roles for r in roles):
            return admin

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required one of: {', '.join(self.allowed_roles)}",
        )
