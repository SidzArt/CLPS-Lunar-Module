"""Public rate-limited API endpoint for support/contact submissions."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.rate_limit import contact_rate_limiter
from app.db.session import get_db
from app.schemas.contact import ContactSubmitIn, ContactSubmitOut
from app.services import contact_service

router = APIRouter(prefix="/contact", tags=["Support & Contact"])


@router.post(
    "",
    response_model=ContactSubmitOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(contact_rate_limiter)],
    summary="Submit a support or inquiry message",
    description="Validates contact payload, checks honeypot field, and persists submission in PostgreSQL.",
)
def submit_contact(
    payload: ContactSubmitIn,
    db: Session = Depends(get_db),
) -> ContactSubmitOut:
    """Record inbound support/contact inquiry safely without exposing SMTP details."""
    return contact_service.submit_contact_message(db, payload)
