"""Pydantic v2 contracts for public Support & Contact submissions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ContactSubmitIn(BaseModel):
    """Inbound contact form payload matching Backend Spec p. 19."""

    sender_name: str = Field(..., min_length=2, max_length=100)
    sender_email: str = Field(..., min_length=5, max_length=255)
    subject: str = Field(..., min_length=3, max_length=200)
    message_body: str = Field(..., min_length=10, max_length=4000)
    website: str = Field(
        default="",
        max_length=200,
        description="Honeypot spam-trap field; bots filling it are flagged.",
    )

    @field_validator("sender_email")
    @classmethod
    def validate_email_syntax(cls, value: str) -> str:
        """Perform lightweight RFC-compatible email format validation."""
        cleaned = value.strip()
        local, sep, domain = cleaned.partition("@")
        if not sep or not local or "." not in domain or " " in cleaned:
            raise ValueError("Please provide a valid email address.")
        return cleaned


class ContactSubmitOut(BaseModel):
    """Sanitized confirmation response returned to the caller."""

    message_id: UUID
    status: str
    received_at: datetime
    notice: str
