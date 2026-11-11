"""Audit logging service for tracking admin actions and dataset imports."""

from typing import Any

from sqlalchemy.orm import Session

from app.models.admin import AuditLog

SENSITIVE_AUDIT_MARKERS = (
    "password",
    "secret",
    "token",
    "signature",
    "authorization",
    "cookie",
    "psk",
)


def redact_audit_value(value: Any) -> Any:
    """Recursively mask sensitive credentials inside audit snapshot payloads."""
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for k, v in value.items():
            key_lower = str(k).lower()
            if any(marker in key_lower for marker in SENSITIVE_AUDIT_MARKERS):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = redact_audit_value(v)
        return sanitized
    if isinstance(value, list):
        return [redact_audit_value(item) for item in value]
    return value


def log_audit(
    db: Session,
    action_key: str,
    entity_type: str,
    entity_id: str | None = None,
    admin_id: str | None = None,
    before_snapshot: dict[str, Any] | None = None,
    after_snapshot: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Persist an audit log entry with sensitive fields automatically redacted."""
    # Sanitize IP address for INET type
    valid_ip = None
    if ip_address == "testclient":
        valid_ip = "127.0.0.1"
    elif ip_address:
        import ipaddress

        try:
            ipaddress.ip_address(ip_address)
            valid_ip = ip_address
        except ValueError:
            valid_ip = None

    safe_before = redact_audit_value(before_snapshot) if before_snapshot is not None else None
    safe_after = redact_audit_value(after_snapshot) if after_snapshot is not None else None

    entry = AuditLog(
        admin_id=admin_id,
        action_key=action_key,
        entity_type=entity_type,
        entity_id=entity_id,
        before_snapshot=safe_before,
        after_snapshot=safe_after,
        ip_address=valid_ip,
    )
    db.add(entry)
    db.flush()
    return entry
