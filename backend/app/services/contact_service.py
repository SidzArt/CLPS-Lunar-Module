"""Service persisting inbound contact messages into PostgreSQL cleanly."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.operations import ContactMessage
from app.schemas.contact import ContactSubmitIn, ContactSubmitOut


def submit_contact_message(db: Session, payload: ContactSubmitIn) -> ContactSubmitOut:
    """Validate, detect honeypot spam, and store contact submission cleanly."""
    is_spam = bool(payload.website.strip())
    record = ContactMessage(
        sender_name=payload.sender_name.strip(),
        sender_email=payload.sender_email.strip(),
        subject=payload.subject.strip(),
        message_body=payload.message_body.strip(),
        is_spam=is_spam,
        status="RECEIVED",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return ContactSubmitOut(
        message_id=record.message_id,
        status=record.status,
        received_at=record.created_at,
        notice=(
            "Message recorded cleanly."
            if not is_spam
            else "Submission accepted for moderation review."
        ),
    )
