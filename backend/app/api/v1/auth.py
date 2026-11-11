"""Administrator authentication endpoints: login, lockout, rotation, CSRF, logout, profile."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.audit import log_audit
from app.core.auth_dependency import get_admin_roles, get_current_admin, hash_token
from app.core.config import settings
from app.core.csrf import (
    clear_csrf_cookie,
    enforce_csrf_for_cookie_request,
    is_request_cookie_secure,
    issue_csrf_cookie,
    validate_origin,
)
from app.core.rate_limit import auth_login_rate_limiter
from app.core.security import (
    generate_secure_token,
    hash_password,
    validate_password_policy,
    verify_password,
)
from app.db.session import get_db
from app.models.admin import Admin, AdminSession
from app.schemas.auth import (
    AdminAuthOut,
    AdminChangePasswordIn,
    AdminLoginIn,
    AdminProfileOut,
    CsrfTokenOut,
)

router = APIRouter(prefix="/auth", tags=["Admin Auth"])


def _resolve_client_ip(request: Request) -> str | None:
    """Resolve and validate client IP string compatible with PostgreSQL INET."""
    import ipaddress

    forwarded_for = request.headers.get("x-forwarded-for")
    candidate = (
        forwarded_for.split(",")[0].strip()
        if forwarded_for
        else (request.client.host if request.client else None)
    )
    if candidate == "testclient":
        return "127.0.0.1"
    if not candidate:
        return None
    try:
        ipaddress.ip_address(candidate)
        return candidate
    except ValueError:
        return None


def _issue_session_and_cookies(
    *,
    db: Session,
    admin: Admin,
    request: Request,
    response: Response,
) -> tuple[str, str]:
    """Create a fresh revocable AdminSession and set HttpOnly session + double-submit CSRF cookies."""
    raw_token = generate_secure_token(32)
    token_hash = hash_token(raw_token)
    expires_at = datetime.now(UTC) + timedelta(hours=settings.SESSION_EXPIRE_HOURS)

    session_record = AdminSession(
        admin_id=admin.admin_id,
        token_hash=token_hash,
        ip_address=_resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        expires_at=expires_at,
        is_revoked=False,
    )
    db.add(session_record)
    db.flush()

    cookie_secure = is_request_cookie_secure(request)
    response.set_cookie(
        key="clps_session",
        value=raw_token,
        max_age=settings.SESSION_EXPIRE_HOURS * 3600,
        httponly=True,
        secure=cookie_secure,
        samesite="lax",
        path="/",
    )
    csrf_token = issue_csrf_cookie(response, request, raw_session_token=raw_token)
    return raw_token, csrf_token


def _to_profile_out(db: Session, admin: Admin) -> AdminProfileOut:
    """Serialize Admin ORM row and assigned RBAC role keys without secret attributes."""
    roles = get_admin_roles(db, str(admin.admin_id))
    return AdminProfileOut(
        admin_id=admin.admin_id,
        username=admin.username,
        display_name=admin.display_name,
        is_active=admin.is_active,
        password_must_rotate=bool(admin.password_must_rotate),
        last_login_at=admin.last_login_at,
        roles=roles,
    )


@router.get(
    "/csrf",
    response_model=CsrfTokenOut,
    summary="Issue double-submit CSRF token synced to active session cookie",
)
def get_csrf_token(
    request: Request,
    response: Response,
    clps_session: Annotated[str | None, Cookie()] = None,
) -> CsrfTokenOut:
    """Issue a double-submit CSRF cookie bound cleanly to the caller's session if present."""
    csrf_token = issue_csrf_cookie(response, request, raw_session_token=clps_session)
    return CsrfTokenOut(csrf_token=csrf_token)


@router.post(
    "/login",
    response_model=AdminAuthOut,
    dependencies=[Depends(auth_login_rate_limiter)],
    summary="Admin login",
    description="Authenticates administrator credentials with rate-limit, lockout, session rotation, and CSRF cookie.",
)
def admin_login(
    payload: AdminLoginIn,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    clps_session: Annotated[str | None, Cookie()] = None,
) -> AdminAuthOut:
    """Authenticate administrator, enforce lockout/rotation, and set HttpOnly + CSRF cookies."""
    validate_origin(request)
    client_ip = _resolve_client_ip(request)
    now = datetime.now(UTC)
    username = payload.username.strip()

    stmt = select(Admin).where(Admin.username == username)
    admin = db.scalar(stmt)

    if admin and admin.locked_until and admin.locked_until > now:
        log_audit(
            db,
            action_key="AUTH_LOGIN_LOCKED",
            entity_type="admins",
            entity_id=str(admin.admin_id),
            admin_id=str(admin.admin_id),
            after_snapshot={"username": admin.username},
            ip_address=client_ip,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account is temporarily locked due to repeated failed login attempts.",
        )

    if not admin or not verify_password(payload.password, admin.password_hash):
        if admin is not None:
            admin.failed_login_count = int(admin.failed_login_count or 0) + 1
            if admin.failed_login_count >= settings.AUTH_LOCKOUT_THRESHOLD:
                admin.locked_until = now + timedelta(minutes=settings.AUTH_LOCKOUT_MINUTES)
            log_audit(
                db,
                action_key="AUTH_LOGIN_FAILED",
                entity_type="admins",
                entity_id=str(admin.admin_id),
                admin_id=str(admin.admin_id),
                after_snapshot={
                    "username": admin.username,
                    "failed_login_count": admin.failed_login_count,
                    "locked": bool(admin.locked_until and admin.locked_until > now),
                },
                ip_address=client_ip,
            )
            db.commit()
        else:
            log_audit(
                db,
                action_key="AUTH_LOGIN_FAILED",
                entity_type="admins",
                entity_id=None,
                admin_id=None,
                after_snapshot={"username": username, "reason": "unknown_account"},
                ip_address=client_ip,
            )
            db.commit()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    if not admin.is_active:
        log_audit(
            db,
            action_key="AUTH_LOGIN_INACTIVE",
            entity_type="admins",
            entity_id=str(admin.admin_id),
            admin_id=str(admin.admin_id),
            ip_address=client_ip,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator account has been deactivated.",
        )

    # Rotate any prior session cookie carried into login (prevent session fixation)
    if clps_session:
        prev_hash = hash_token(clps_session)
        prev_rec = db.scalar(select(AdminSession).where(AdminSession.token_hash == prev_hash))
        if prev_rec and not prev_rec.is_revoked:
            prev_rec.is_revoked = True

    raw_token, csrf_token = _issue_session_and_cookies(
        db=db,
        admin=admin,
        request=request,
        response=response,
    )

    admin.last_login_at = now
    admin.failed_login_count = 0
    admin.locked_until = None

    log_audit(
        db,
        action_key="AUTH_LOGIN_SUCCESS",
        entity_type="admins",
        entity_id=str(admin.admin_id),
        admin_id=str(admin.admin_id),
        after_snapshot={"username": admin.username},
        ip_address=client_ip,
    )
    db.commit()

    return AdminAuthOut(
        status="AUTHENTICATED",
        session_token=raw_token,
        csrf_token=csrf_token,
        admin=_to_profile_out(db, admin),
    )


@router.post(
    "/logout",
    summary="Admin logout",
    description="Revokes the active session token in PostgreSQL and clears session and CSRF cookies.",
)
def admin_logout(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    clps_session: Annotated[str | None, Cookie()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    """Revoke session in database and clear browser cookies cleanly."""
    raw_token: str | None = None
    used_cookie = False
    if authorization and authorization.startswith("Bearer "):
        candidate = authorization.split(" ", 1)[1].strip()
        if candidate:
            raw_token = candidate
    if not raw_token and clps_session:
        raw_token = clps_session
        used_cookie = True

    if used_cookie and raw_token:
        enforce_csrf_for_cookie_request(request, raw_token)

    if raw_token:
        token_hash = hash_token(raw_token)
        stmt = select(AdminSession).where(AdminSession.token_hash == token_hash)
        session_record = db.scalar(stmt)
        if session_record:
            session_record.is_revoked = True
            log_audit(
                db,
                action_key="AUTH_LOGOUT",
                entity_type="admin_sessions",
                entity_id=str(session_record.session_id),
                admin_id=str(session_record.admin_id),
                ip_address=_resolve_client_ip(request),
            )
            db.commit()

    response.delete_cookie(key="clps_session", path="/")
    clear_csrf_cookie(response)
    return {"status": "LOGGED_OUT", "message": "Admin session revoked successfully."}


@router.get(
    "/me",
    response_model=AdminProfileOut,
    summary="Get active admin profile",
    description="Returns authenticated administrator identity and roles.",
)
def get_my_profile(
    request: Request,
    response: Response,
    admin: Annotated[Admin, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> AdminProfileOut:
    """Return profile of currently authenticated administrator."""
    if getattr(request.state, "auth_method", None) == "cookie" and not request.cookies.get(
        "clps_csrf"
    ):
        issue_csrf_cookie(
            response,
            request,
            raw_session_token=getattr(request.state, "raw_session_token", None),
        )
    return _to_profile_out(db, admin)


@router.post(
    "/change-password",
    response_model=AdminAuthOut,
    summary="Change authenticated admin password and rotate sessions",
)
def change_my_password(
    payload: AdminChangePasswordIn,
    request: Request,
    response: Response,
    admin: Annotated[Admin, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> AdminAuthOut:
    """Validate current password, enforce complexity, revoke all prior sessions, and rotate."""
    if not verify_password(payload.current_password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect.",
        )
    if verify_password(payload.new_password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must differ from current password.",
        )
    try:
        validate_password_policy(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    now = datetime.now(UTC)
    admin.password_hash = hash_password(payload.new_password)
    admin.password_updated_at = now
    admin.password_must_rotate = False

    # Revoke all active sessions for this admin on password rotation
    db.execute(
        update(AdminSession)
        .where(AdminSession.admin_id == admin.admin_id, AdminSession.is_revoked.is_(False))
        .values(is_revoked=True)
    )

    raw_token, csrf_token = _issue_session_and_cookies(
        db=db,
        admin=admin,
        request=request,
        response=response,
    )
    log_audit(
        db,
        action_key="AUTH_PASSWORD_CHANGED",
        entity_type="admins",
        entity_id=str(admin.admin_id),
        admin_id=str(admin.admin_id),
        after_snapshot={"sessions_rotated": True},
        ip_address=_resolve_client_ip(request),
    )
    db.commit()

    return AdminAuthOut(
        status="AUTHENTICATED",
        session_token=raw_token,
        csrf_token=csrf_token,
        admin=_to_profile_out(db, admin),
    )
