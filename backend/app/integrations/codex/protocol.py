"""CODEX Protocol v1 command schema, HMAC-SHA256 signing, redaction, and Uno UART framing."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import struct
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

PROTOCOL_VERSION = "codex.v1"
UART_SOF = 0xAA55
UART_VERSION = 0x01
UART_MAX_PAYLOAD_BYTES = 256

# Uno framed binary packet message types
UART_MSG_PING = 0x01
UART_MSG_MOTION_CMD = 0x02
UART_MSG_ESTOP = 0x03
UART_MSG_STATUS_REQ = 0x04
UART_MSG_ACK = 0x81
UART_MSG_NACK = 0x82
UART_MSG_FAULT = 0x83
UART_MSG_TELEMETRY = 0x84

SENSITIVE_KEY_MARKERS = ("signature", "secret", "token", "password", "authorization", "psk")


class UartFrameError(ValueError):
    """Raised when a framed Uno UART packet fails SOF, version, length, or CRC16 checks."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class DecodedUartFrame:
    """Verified binary UART packet decoded after CRC16-CCITT check."""

    version: int
    msg_type: int
    sequence_number: int
    payload: bytes
    crc16: int


def generate_command_nonce() -> str:
    """Generate cryptographically strong 128-bit command nonce hex string."""
    return secrets.token_hex(16)


def canonical_payload_json(payload: dict[str, Any]) -> str:
    """Serialize payload deterministically for SHA-256 digest and HMAC signature binding."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_payload_sha256(payload: dict[str, Any]) -> str:
    """Compute SHA-256 digest of canonical JSON payload."""
    return hashlib.sha256(canonical_payload_json(payload).encode("utf-8")).hexdigest()


def build_codex_command_payload(
    *,
    command_id: str,
    simulation_id: str,
    site_id: int,
    sequence_number: int,
    ttl_seconds: int,
    device_targets: list[str],
    configuration_version: str,
    calibration_version: str | None,
    led_mapping_version: str | None,
    motor_commands: dict[str, Any] | None,
    moon_led: dict[str, Any] | None,
    idempotency_key: str | None = None,
    nonce: str | None = None,
    issued_at_utc: datetime | None = None,
) -> dict[str, Any]:
    """Construct complete Version 1 CODEX hardware command payload."""
    issued = (issued_at_utc or datetime.now(UTC)).astimezone(UTC)
    expires = issued + timedelta(seconds=ttl_seconds)
    return {
        "protocol_version": PROTOCOL_VERSION,
        "command_id": command_id,
        "simulation_id": simulation_id,
        "site_id": site_id,
        "issued_at_utc": issued.isoformat(),
        "expires_at_utc": expires.isoformat(),
        "nonce": nonce or generate_command_nonce(),
        "sequence_number": sequence_number,
        "idempotency_key": idempotency_key,
        "device_targets": list(device_targets),
        "configuration_version": configuration_version,
        "calibration_version": calibration_version,
        "led_mapping_version": led_mapping_version,
        "motor_commands": motor_commands,
        "moon_led": moon_led,
    }


def sign_codex_command(
    shared_secret: str,
    *,
    command_id: str,
    issued_at_utc: str,
    nonce: str,
    sequence_number: int,
    payload: dict[str, Any],
) -> str:
    """Compute HMAC-SHA256 hex digest binding metadata headers and canonical JSON body."""
    canonical_body = canonical_payload_json(payload)
    signing_input = f"{command_id}.{issued_at_utc}.{nonce}.{sequence_number}.{canonical_body}"
    return hmac.new(
        shared_secret.encode("utf-8"),
        signing_input.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_codex_signature(
    shared_secret: str,
    *,
    provided_signature: str,
    command_id: str,
    issued_at_utc: str,
    nonce: str,
    sequence_number: int,
    payload: dict[str, Any],
) -> bool:
    """Verify HMAC-SHA256 signature in constant time using hmac.compare_digest."""
    if not provided_signature:
        return False
    expected = sign_codex_command(
        shared_secret,
        command_id=command_id,
        issued_at_utc=issued_at_utc,
        nonce=nonce,
        sequence_number=sequence_number,
        payload=payload,
    )
    return hmac.compare_digest(expected, provided_signature.strip().lower())


def build_signed_headers(shared_secret: str, payload: dict[str, Any]) -> dict[str, str]:
    """Construct outbound HTTP authentication headers for ESP32 / ESP32-S3 controllers."""
    sig = sign_codex_command(
        shared_secret,
        command_id=str(payload["command_id"]),
        issued_at_utc=str(payload["issued_at_utc"]),
        nonce=str(payload["nonce"]),
        sequence_number=int(payload["sequence_number"]),
        payload=payload,
    )
    return {
        "Content-Type": "application/json",
        "X-Codex-Protocol": PROTOCOL_VERSION,
        "X-Codex-Command-Id": str(payload["command_id"]),
        "X-Codex-Timestamp": str(payload["issued_at_utc"]),
        "X-Codex-Nonce": str(payload["nonce"]),
        "X-Codex-Sequence": str(payload["sequence_number"]),
        "X-Codex-Signature": sig,
    }


def redact_sensitive_mapping(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively mask HMAC signatures, tokens, and secrets before logging or API serialization."""
    redacted: dict[str, Any] = {}
    for key, val in data.items():
        lowered = key.lower()
        if any(marker in lowered for marker in SENSITIVE_KEY_MARKERS):
            redacted[key] = "[REDACTED]"
        elif isinstance(val, dict):
            redacted[key] = redact_sensitive_mapping(val)
        else:
            redacted[key] = val
    return redacted


def crc16_ccitt(data: bytes) -> int:
    """Compute standard CRC16-CCITT (poly 0x1021, initial value 0xFFFF)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = (((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)) & 0xFFFF
    return crc


def encode_uno_uart_frame(msg_type: int, sequence_number: int, payload: bytes) -> bytes:
    """Encode a CRC16-protected binary UART frame for ESP32 <-> Arduino Uno link."""
    if sequence_number < 0 or sequence_number > 0xFFFFFFFF:
        raise UartFrameError("invalid_sequence", "UART sequence_number must fit in uint32.")
    if len(payload) > UART_MAX_PAYLOAD_BYTES:
        raise UartFrameError(
            "payload_too_large",
            f"UART payload length {len(payload)} exceeds {UART_MAX_PAYLOAD_BYTES} bytes.",
        )

    header_body = (
        struct.pack("<BBIH", UART_VERSION, msg_type & 0xFF, sequence_number, len(payload)) + payload
    )
    crc = crc16_ccitt(header_body)
    return struct.pack("<H", UART_SOF) + header_body + struct.pack("<H", crc)


def decode_uno_uart_frame(raw_frame: bytes) -> DecodedUartFrame:
    """Validate and decode a framed Uno UART packet, raising UartFrameError on corruption."""
    if len(raw_frame) < 12:
        raise UartFrameError(
            "truncated_frame",
            f"UART frame too short ({len(raw_frame)} bytes; minimum is 12).",
        )

    sof, version, msg_type, seq, length = struct.unpack("<HBBIH", raw_frame[:10])
    if sof != UART_SOF:
        raise UartFrameError(
            "invalid_sof", f"Unexpected SOF 0x{sof:04X}; expected 0x{UART_SOF:04X}."
        )
    if version != UART_VERSION:
        raise UartFrameError(
            "unsupported_uart_version", f"Unsupported UART version 0x{version:02X}."
        )
    if len(raw_frame) != 10 + length + 2:
        raise UartFrameError(
            "length_mismatch",
            f"Declared payload length {length} does not match frame size {len(raw_frame)}.",
        )

    body_for_crc = raw_frame[2 : 10 + length]
    payload = raw_frame[10 : 10 + length]
    (received_crc,) = struct.unpack("<H", raw_frame[10 + length : 12 + length])
    computed_crc = crc16_ccitt(body_for_crc)
    if received_crc != computed_crc:
        raise UartFrameError(
            "crc_mismatch",
            f"UART CRC16 mismatch: received 0x{received_crc:04X}, computed 0x{computed_crc:04X}.",
        )

    return DecodedUartFrame(
        version=version,
        msg_type=msg_type,
        sequence_number=seq,
        payload=payload,
        crc16=received_crc,
    )


def encode_uno_motion_payload(
    *,
    nema17_plan: dict[str, Any] | None,
    byj_plan: dict[str, Any] | None,
    physical_duration_seconds: int,
) -> bytes:
    """Pack compact fixed-syntax motor steps into bounded UART payload for Uno parsing."""
    n_dir = 1 if (nema17_plan and int(nema17_plan.get("hardware_direction", 1)) >= 0) else 0
    n_steps = int(nema17_plan.get("total_steps", 0)) if nema17_plan else 0
    n_us = int(nema17_plan.get("step_interval_us", 0)) if nema17_plan else 0

    b_dir = 1 if (byj_plan and int(byj_plan.get("hardware_direction", 1)) >= 0) else 0
    b_steps = int(byj_plan.get("total_steps", 0)) if byj_plan else 0
    b_us = int(byj_plan.get("step_interval_us", 0)) if byj_plan else 0

    compact = f"N:{n_dir}:{n_steps}:{n_us}|B:{b_dir}:{b_steps}:{b_us}|T:{physical_duration_seconds}"
    return compact.encode("ascii")
