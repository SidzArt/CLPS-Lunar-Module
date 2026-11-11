"""CLPS Luna Browser - FastAPI Application Entry Point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.admin.audit import router as admin_audit_router
from app.api.v1.admin.codex_admin import router as admin_codex_router
from app.api.v1.admin.imports_admin import router as admin_imports_router
from app.api.v1.admin.media_admin import router as admin_media_router
from app.api.v1.admin.simulations_admin import router as admin_simulations_router
from app.api.v1.admin.sites_admin import router as admin_sites_router
from app.api.v1.admin.users import router as admin_users_router
from app.api.v1.ai_assist import router as ai_assist_router
from app.api.v1.auth import router as auth_router
from app.api.v1.codex import router as codex_router
from app.api.v1.compare import router as compare_router
from app.api.v1.contact import router as contact_router
from app.api.v1.health import router as health_router
from app.api.v1.search import router as search_router
from app.api.v1.simulations import router as simulations_router
from app.api.v1.sites import router as sites_router
from app.core.config import settings
from app.core.logging import logger, setup_logging
from app.core.middleware import RequestIdMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle management."""
    setup_logging(debug=settings.DEBUG)
    logger.info("Initializing CLPS Luna Browser Backend")
    logger.info("Environment: %s | Debug: %s", settings.APP_ENV, settings.DEBUG)
    Path(settings.MEDIA_ROOT).mkdir(parents=True, exist_ok=True)
    yield
    logger.info("Shutting down CLPS Luna Browser Backend")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    description="Scientific API and simulation platform for NASA CLPS lunar exploration.",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
)

# Security and request ID middleware
app.add_middleware(RequestIdMiddleware)

# Cross-Origin Resource Sharing (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-Process-Time"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Standardized handler for Pydantic input validation failures."""
    request_id = getattr(request.state, "request_id", None)
    errors = [
        {"field": ".".join(str(loc) for loc in err["loc"]), "message": err["msg"]}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "code": "VALIDATION_ERROR",
            "message": "Input validation failed. Inspect field errors.",
            "field_errors": errors,
            "request_id": request_id,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Standardized handler for uncaught server exceptions."""
    request_id = getattr(request.state, "request_id", None)
    logger.exception("Unhandled server exception: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An internal server error occurred.",
            "field_errors": [],
            "request_id": request_id,
        },
    )


# Static media asset mount
media_storage_path = Path(settings.MEDIA_ROOT)
media_storage_path.mkdir(parents=True, exist_ok=True)
app.mount("/storage/media", StaticFiles(directory=str(media_storage_path)), name="media")


# Register API v1 routers
app.include_router(health_router, prefix=settings.API_V1_STR)
app.include_router(sites_router, prefix=settings.API_V1_STR)
app.include_router(search_router, prefix=settings.API_V1_STR)
app.include_router(compare_router, prefix=settings.API_V1_STR)
app.include_router(ai_assist_router, prefix=settings.API_V1_STR)
app.include_router(simulations_router, prefix=settings.API_V1_STR)
app.include_router(codex_router, prefix=settings.API_V1_STR)
app.include_router(contact_router, prefix=settings.API_V1_STR)
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(admin_sites_router, prefix=settings.API_V1_STR)
app.include_router(admin_media_router, prefix=settings.API_V1_STR)
app.include_router(admin_imports_router, prefix=settings.API_V1_STR)
app.include_router(admin_simulations_router, prefix=settings.API_V1_STR)
app.include_router(admin_codex_router, prefix=settings.API_V1_STR)
app.include_router(admin_users_router, prefix=settings.API_V1_STR)
app.include_router(admin_audit_router, prefix=settings.API_V1_STR)

# Convenience root routing for container/health monitors
app.include_router(health_router)
