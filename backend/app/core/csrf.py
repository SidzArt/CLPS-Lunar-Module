"""Double-submit HMAC-bound CSRF protection and Origin verification."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from urllib.parse import urlparse

from fastapi import HTTPException, Request, Response, status

from app.core.config import settings
from app.core.security import hash_token

CSRF_COOKIE_NAME = "clps_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
UNSAFE_HTTP_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _normalize_origin(raw_url: str) -> str | None:
    """Extract canonical scheme://netloc from Origin or Referer URL."""
    cleaned = raw_url.strip()
    if not cleaned or cleaned.lower() == "null":
        return None
    parsed = urlparse(cleaned)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def allowed_origins_for_request(request: Request) -> set[str]:
    """Build exact allow-list of permitted browser origins for current deployment/request."""
    allowed = {o.strip().rstrip("/").lower() for o in settings.cors_origins_list if o.strip()}
    if settings.PUBLIC_BASE_URL:
        norm_pub = _normalize_origin(settings.PUBLIC_BASE_URL)
        if norm_pub:
            allowed.add(norm_pub)

    # Same-origin from HTTP Host / forwarded headers
    scheme = (
        (request.headers.get("x-forwarded-proto") or request.url.scheme or "http")
        .split(",")[0]
        .strip()
        .lower()
    )
    host = (
        (
            request.headers.get("x-forwarded-host")
            or request.headers.get("host")
            or request.url.netloc
            or ""
        )
        .split(",")[0]
        .strip()
        .lower()
    )
    if host:
        allowed.add(f"{scheme}://{host}")
    return allowed


def validate_origin(request: Request) -> None:
    """Reject cross-site unsafe requests whose Origin or Referer is outside allowed origins."""
    allowed = allowed_origins_for_request(request)

    origin = request.headers.get("origin")
    if origin is not None:
        normalized = _normalize_origin(origin)
        if normalized is None or normalized not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cross-origin request rejected by CSRF Origin protection.",
            )
        return

    referer = request.headers.get("referer")
    if referer is not None:
        normalized_ref = _normalize_origin(referer)
        if normalized_ref is None or normalized_ref not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cross-origin Referer rejected by CSRF protection.",
            )


def _sign_csrf_value(session_binding: str, nonce: str) -> str:
    """Sign CSRF nonce bound to active session digest using server HMAC key."""
    msg = f"{session_binding}:{nonce}".encode()
    digest = hmac.new(settings.SESSION_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return f"{nonce}.{digest}"


def create_csrf_token_for_session(raw_session_token: str | None) -> str:
    """Create a fresh signed CSRF token tied to the session token hash (or 'anon')."""
    binding = hash_token(raw_session_token) if raw_session_token else "anon"
    nonce = secrets.token_urlsafe(24)
    return _sign_csrf_value(binding, nonce)


def verify_csrf_token_value(token: str, raw_session_token: str | None) -> bool:
    """Verify CSRF token format and constant-time HMAC signature against session binding."""
    if not token or "." not in token:
        return False
    nonce, provided_mac = token.split(".", 1)
    if not nonce or not provided_mac:
        return False
    binding = hash_token(raw_session_token) if raw_session_token else "anon"
    expected_token = _sign_csrf_value(binding, nonce)
    expected_mac = expected_token.split(".", 1)[1]
    return hmac.compare_digest(expected_mac, provided_mac.strip().lower())


def is_request_cookie_secure(request: Request) -> bool:
    """Evaluate Secure flag cleanly for localhost HTTP dev vs HTTPS/production."""
    return settings.is_cookie_secure(
        request_scheme=request.url.scheme,
        forwarded_proto=request.headers.get("x-forwarded-proto"),
    )


def issue_csrf_cookie(
    response: Response,
    request: Request,
    *,
    raw_session_token: str | None,
) -> str:
    """Generate and set double-submit readable CSRF cookie bound to active session."""
    csrf_value = create_csrf_token_for_session(raw_session_token)
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_value,
        max_age=settings.SESSION_EXPIRE_HOURS * 3600,
        httponly=False,
        secure=is_request_cookie_secure(request),
        samesite="lax",
        path="/",
    )
    return csrf_value


def clear_csrf_cookie(response: Response) -> None:
    """Clear readable CSRF cookie cleanly on logout or session teardown."""
    response.delete_cookie(key=CSRF_COOKIE_NAME, path="/")


def enforce_csrf_for_cookie_request(request: Request, raw_session_token: str) -> None:
    """Enforce Origin check and HMAC-bound double-submit CSRF token on unsafe cookie requests."""
    if request.method.upper() not in UNSAFE_HTTP_METHODS:
        return

    validate_origin(request)

    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
    csrf_header = request.headers.get(CSRF_HEADER_NAME)
    if not csrf_cookie or not csrf_header:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed: missing CSRF cookie or X-CSRF-Token header.",
        )

    if not hmac.compare_digest(csrf_cookie.strip(), csrf_header.strip()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed: cookie and header token mismatch.",
        )

    if not verify_csrf_token_value(csrf_header.strip(), raw_session_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed: token signature invalid for active session.",
        )
