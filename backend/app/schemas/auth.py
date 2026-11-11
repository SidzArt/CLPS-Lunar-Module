"""Pydantic schemas for administrator authentication and sessions."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AdminLoginIn(BaseModel):
    """Admin login credentials."""

    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8, max_length=256)


class AdminChangePasswordIn(BaseModel):
    """Authenticated administrator password rotation payload."""

    current_password: str = Field(..., min_length=8, max_length=256)
    new_password: str = Field(..., min_length=12, max_length=256)


class AdminProfileOut(BaseModel):
    """Authenticated administrator profile."""

    admin_id: uuid.UUID
    username: str
    display_name: str | None = None
    is_active: bool
    password_must_rotate: bool = False
    last_login_at: datetime | None = None
    roles: list[str] = Field(default_factory=list)


class AdminAuthOut(BaseModel):
    """Successful login response envelope."""

    status: str = "AUTHENTICATED"
    session_token: str
    csrf_token: str
    admin: AdminProfileOut


class CsrfTokenOut(BaseModel):
    """CSRF token issuance payload for SPA double-submit cookie verification."""

    csrf_token: str
