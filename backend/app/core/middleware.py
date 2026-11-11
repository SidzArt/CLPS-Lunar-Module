"""HTTP middleware for Request ID propagation, strict security headers, and timing."""

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.logging import request_id_ctx


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assigns X-Request-ID, timing header, and defense-in-depth HTTP security headers."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Check incoming header or generate clean 16-hex request ID
        incoming_id = request.headers.get("X-Request-ID")
        request_id = incoming_id if incoming_id else f"req_{uuid.uuid4().hex[:16]}"
        token = request_id_ctx.set(request_id)
        request.state.request_id = request_id

        start_time = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)

        process_time = time.perf_counter() - start_time
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{process_time:.4f}s"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), usb=()"

        # Strict non-HTML Content-Security-Policy on API JSON routes (leave Swagger docs usable)
        path = request.url.path
        if path.startswith("/api/") and path not in (
            f"{settings.API_V1_STR}/docs",
            f"{settings.API_V1_STR}/redoc",
            f"{settings.API_V1_STR}/openapi.json",
        ):
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'"
            )

        forwarded_proto = (
            (request.headers.get("x-forwarded-proto") or request.url.scheme or "http")
            .split(",")[0]
            .strip()
            .lower()
        )
        if settings.ENABLE_HSTS and (
            forwarded_proto == "https" or settings.APP_ENV.lower() == "production"
        ):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response
