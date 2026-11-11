"""Mock and HTTP transports for communicating with ESP32 bridge, Arduino Uno, and ESP32-S3."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.core.config import settings
from app.integrations.codex.protocol import (
    UART_MSG_ESTOP,
    UART_MSG_MOTION_CMD,
    UartFrameError,
    decode_uno_uart_frame,
    redact_sensitive_mapping,
    verify_codex_signature,
)

logger = logging.getLogger("clps_luna_browser.codex.transport")


@dataclass(frozen=True)
class DeviceProbeResult:
    """Point-in-time probe telemetry reported by a CODEX controller."""

    controller_key: str
    online: bool
    ping_latency_ms: float | None
    reported_firmware_version: str | None
    reported_firmware_checksum: str | None
    uart_ok: bool
    driver_config_ok: bool
    led_controller_ok: bool
    estop_latched: bool
    battery_voltage_available: bool = False
    battery_voltage_v: float | None = None
    error_code: str | None = None
    error_message: str | None = None
    telemetry: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ControllerDispatchAck:
    """Controller acknowledgement returned immediately after authenticated command dispatch."""

    controller_key: str
    ack_status: (
        str  # 'accepted' | 'started' | 'completed' | 'rejected' | 'fault' | 'timeout' | 'estopped'
    )
    device_sequence: int | None
    message: str
    telemetry: dict[str, Any] = field(default_factory=dict)


class CodexTransport(Protocol):
    """Transport abstraction separating software protocol/dispatch from bench vs mock targets."""

    mode_name: str

    def probe_device(
        self,
        *,
        controller_key: str,
        endpoint_host: str | None,
        endpoint_port: int | None,
        expected_firmware_version: str | None,
        device_metadata: dict[str, Any] | None = None,
    ) -> DeviceProbeResult:
        """Probe controller health, firmware identity, and subordinate link flags."""

    def dispatch_command(
        self,
        *,
        controller_key: str,
        endpoint_host: str | None,
        endpoint_port: int | None,
        command_payload: dict[str, Any],
        signed_headers: dict[str, str],
        uart_frame: bytes | None = None,
    ) -> ControllerDispatchAck:
        """Send signed Command v1 payload (and Uno UART frame if bridge) to controller."""

    def dispatch_estop(
        self,
        *,
        controller_key: str,
        endpoint_host: str | None,
        endpoint_port: int | None,
        command_payload: dict[str, Any],
        signed_headers: dict[str, str],
        uart_frame: bytes | None = None,
    ) -> ControllerDispatchAck:
        """Transmit highest-priority emergency stop command to controller."""


class MockCodexTransport:
    """In-memory deterministic bench simulator enforcing HMAC and Uno UART CRC16 checks."""

    mode_name = "mock"

    def __init__(self, shared_secret: str | None = None) -> None:
        self.shared_secret = shared_secret or settings.CODEX_SHARED_SECRET
        # Optional fault injection map keyed by controller_key
        self.behaviors: dict[str, dict[str, Any]] = {}
        self.dispatched_commands: list[dict[str, Any]] = []
        self.seen_nonces: dict[str, set[str]] = {}
        self.last_sequence: dict[str, int] = {}

    def configure_device(self, controller_key: str, **behavior: Any) -> None:
        """Set mock device state (e.g., offline=True, timeout=True, firmware_version=...)."""
        current = self.behaviors.get(controller_key, {})
        current.update(behavior)
        self.behaviors[controller_key] = current

    def reset(self) -> None:
        """Clear mock behaviors and captured command history."""
        self.behaviors.clear()
        self.dispatched_commands.clear()
        self.seen_nonces.clear()
        self.last_sequence.clear()

    def probe_device(
        self,
        *,
        controller_key: str,
        endpoint_host: str | None,
        endpoint_port: int | None,
        expected_firmware_version: str | None,
        device_metadata: dict[str, Any] | None = None,
    ) -> DeviceProbeResult:
        cfg = self.behaviors.get(controller_key, {})
        if cfg.get("offline", False) or cfg.get("timeout", False):
            return DeviceProbeResult(
                controller_key=controller_key,
                online=False,
                ping_latency_ms=None,
                reported_firmware_version=None,
                reported_firmware_checksum=None,
                uart_ok=False,
                driver_config_ok=False,
                led_controller_ok=False,
                estop_latched=bool(cfg.get("estop_latched", False)),
                error_code="timeout" if cfg.get("timeout") else "unreachable",
                error_message=f"Simulated {controller_key} offline/timeout in mock transport.",
            )

        fw_ver = cfg.get("firmware_version", expected_firmware_version)
        uart_ok = bool(cfg.get("uart_ok", controller_key in ("wifi_bridge", "motion_uno")))
        driver_ok = bool(cfg.get("driver_config_ok", controller_key == "motion_uno"))
        led_ok = bool(cfg.get("led_controller_ok", controller_key == "moon_led_s3"))
        if cfg.get("uart_failure", False):
            uart_ok = False
        return DeviceProbeResult(
            controller_key=controller_key,
            online=True,
            ping_latency_ms=float(cfg.get("ping_latency_ms", 4.2)),
            reported_firmware_version=fw_ver,
            reported_firmware_checksum=cfg.get("firmware_checksum"),
            uart_ok=uart_ok,
            driver_config_ok=driver_ok,
            led_controller_ok=led_ok,
            estop_latched=bool(cfg.get("estop_latched", False)),
            battery_voltage_available=bool(cfg.get("battery_voltage_available", False)),
            battery_voltage_v=cfg.get("battery_voltage_v"),
            error_code=cfg.get("error_code"),
            error_message=cfg.get("error_message"),
            telemetry={"transport": "mock", "endpoint": f"{endpoint_host}:{endpoint_port}"},
        )

    def _verify_and_record(
        self,
        *,
        controller_key: str,
        command_payload: dict[str, Any],
        signed_headers: dict[str, str],
        uart_frame: bytes | None,
        is_estop: bool,
    ) -> ControllerDispatchAck:
        cfg = self.behaviors.get(controller_key, {})
        if cfg.get("timeout", False):
            return ControllerDispatchAck(
                controller_key=controller_key,
                ack_status="timeout",
                device_sequence=None,
                message=f"Simulated request timeout communicating with '{controller_key}'.",
            )
        if cfg.get("offline", False):
            return ControllerDispatchAck(
                controller_key=controller_key,
                ack_status="fault",
                device_sequence=None,
                message=f"Controller '{controller_key}' unreachable.",
            )

        # Verify controller-side HMAC authentication unless simulating auth mismatch
        provided_sig = signed_headers.get("X-Codex-Signature", "")
        valid_hmac = verify_codex_signature(
            self.shared_secret,
            provided_signature=provided_sig,
            command_id=str(command_payload["command_id"]),
            issued_at_utc=str(command_payload["issued_at_utc"]),
            nonce=str(command_payload["nonce"]),
            sequence_number=int(command_payload["sequence_number"]),
            payload=command_payload,
        )
        if not valid_hmac or cfg.get("reject_hmac", False):
            return ControllerDispatchAck(
                controller_key=controller_key,
                ack_status="rejected",
                device_sequence=None,
                message="Controller rejected HMAC-SHA256 authentication.",
            )

        nonce = str(command_payload["nonce"])
        seq = int(command_payload["sequence_number"])
        ctrl_nonces = self.seen_nonces.setdefault(controller_key, set())
        ctrl_last_seq = self.last_sequence.get(controller_key, 0)
        if not is_estop and (nonce in ctrl_nonces or seq <= ctrl_last_seq):
            return ControllerDispatchAck(
                controller_key=controller_key,
                ack_status="rejected",
                device_sequence=ctrl_last_seq,
                message="Controller rejected replayed nonce or non-monotonic sequence.",
            )

        if controller_key in ("wifi_bridge", "motion_uno") and uart_frame is not None:
            try:
                decoded = decode_uno_uart_frame(uart_frame)
                expected_msg = UART_MSG_ESTOP if is_estop else UART_MSG_MOTION_CMD
                if decoded.msg_type != expected_msg:
                    return ControllerDispatchAck(
                        controller_key=controller_key,
                        ack_status="rejected",
                        device_sequence=seq,
                        message="UART message type mismatch on Uno relay.",
                    )
            except UartFrameError as exc:
                return ControllerDispatchAck(
                    controller_key=controller_key,
                    ack_status="fault",
                    device_sequence=seq,
                    message=f"UART frame verification failed: {exc.message}",
                )

        if cfg.get("uart_failure", False) and controller_key in ("wifi_bridge", "motion_uno"):
            return ControllerDispatchAck(
                controller_key=controller_key,
                ack_status="fault",
                device_sequence=seq,
                message="Uno UART NACK / link timeout downstream of Wi-Fi bridge.",
            )

        if cfg.get("simulate_fault", False) and not is_estop:
            return ControllerDispatchAck(
                controller_key=controller_key,
                ack_status="fault",
                device_sequence=seq,
                message="Simulated hardware actuator fault reported after dispatch.",
            )

        self.seen_nonces.setdefault(controller_key, set()).add(nonce)
        self.last_sequence[controller_key] = max(self.last_sequence.get(controller_key, 0), seq)
        self.dispatched_commands.append(
            {
                "controller_key": controller_key,
                "is_estop": is_estop,
                "command_id": command_payload["command_id"],
                "sequence_number": seq,
                "headers": redact_sensitive_mapping(signed_headers),
                "uart_frame_len": len(uart_frame) if uart_frame else 0,
            }
        )
        return ControllerDispatchAck(
            controller_key=controller_key,
            ack_status="estopped" if is_estop else "completed",
            device_sequence=seq,
            message="Mock E-STOP latched." if is_estop else "Mock execution completed cleanly.",
            telemetry={"transport": "mock", "sequence_number": seq},
        )

    def dispatch_command(
        self,
        *,
        controller_key: str,
        endpoint_host: str | None,
        endpoint_port: int | None,
        command_payload: dict[str, Any],
        signed_headers: dict[str, str],
        uart_frame: bytes | None = None,
    ) -> ControllerDispatchAck:
        return self._verify_and_record(
            controller_key=controller_key,
            command_payload=command_payload,
            signed_headers=signed_headers,
            uart_frame=uart_frame,
            is_estop=False,
        )

    def dispatch_estop(
        self,
        *,
        controller_key: str,
        endpoint_host: str | None,
        endpoint_port: int | None,
        command_payload: dict[str, Any],
        signed_headers: dict[str, str],
        uart_frame: bytes | None = None,
    ) -> ControllerDispatchAck:
        return self._verify_and_record(
            controller_key=controller_key,
            command_payload=command_payload,
            signed_headers=signed_headers,
            uart_frame=uart_frame,
            is_estop=True,
        )


class HttpCodexTransport:
    """Real synchronous HTTP-to-ESP32/ESP32-S3 transport with strict timeouts and redaction."""

    mode_name = "http"

    def __init__(self, timeout_seconds: float | None = None) -> None:
        self.timeout_seconds = timeout_seconds or settings.CODEX_REQUEST_TIMEOUT_SECONDS

    def _base_url(self, host: str | None, port: int | None) -> str:
        if not host:
            raise ValueError("Missing device endpoint_host for HTTP CODEX transport.")
        resolved_port = port or 80
        return f"http://{host}:{resolved_port}"

    def probe_device(
        self,
        *,
        controller_key: str,
        endpoint_host: str | None,
        endpoint_port: int | None,
        expected_firmware_version: str | None,
        device_metadata: dict[str, Any] | None = None,
    ) -> DeviceProbeResult:
        try:
            url = f"{self._base_url(endpoint_host, endpoint_port)}/health"
            t0 = time.monotonic()
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.get(url)
            latency_ms = (time.monotonic() - t0) * 1000.0
            resp.raise_for_status()
            data = resp.json()
            return DeviceProbeResult(
                controller_key=controller_key,
                online=True,
                ping_latency_ms=round(latency_ms, 2),
                reported_firmware_version=data.get("firmware_version"),
                reported_firmware_checksum=data.get("firmware_checksum"),
                uart_ok=bool(data.get("uart_ok", False)),
                driver_config_ok=bool(data.get("driver_config_ok", False)),
                led_controller_ok=bool(data.get("led_controller_ok", False)),
                estop_latched=bool(data.get("estop_latched", False)),
                battery_voltage_available=bool(data.get("battery_voltage_available", False)),
                battery_voltage_v=(
                    float(data["battery_voltage_v"])
                    if data.get("battery_voltage_available")
                    and data.get("battery_voltage_v") is not None
                    else None
                ),
                telemetry=data,
            )
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            logger.warning("CODEX HTTP probe failed for %s: %s", controller_key, type(exc).__name__)
            return DeviceProbeResult(
                controller_key=controller_key,
                online=False,
                ping_latency_ms=None,
                reported_firmware_version=None,
                reported_firmware_checksum=None,
                uart_ok=False,
                driver_config_ok=False,
                led_controller_ok=False,
                estop_latched=False,
                error_code="http_probe_failed",
                error_message=f"HTTP probe error ({type(exc).__name__})",
            )

    def _post_command(
        self,
        *,
        controller_key: str,
        endpoint_host: str | None,
        endpoint_port: int | None,
        path: str,
        command_payload: dict[str, Any],
        signed_headers: dict[str, str],
        uart_frame: bytes | None,
    ) -> ControllerDispatchAck:
        try:
            url = f"{self._base_url(endpoint_host, endpoint_port)}{path}"
            body = dict(command_payload)
            if uart_frame is not None:
                body["uart_frame_hex"] = uart_frame.hex()
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.post(url, json=body, headers=signed_headers)
            if resp.status_code in (401, 403):
                return ControllerDispatchAck(
                    controller_key=controller_key,
                    ack_status="rejected",
                    device_sequence=None,
                    message=f"Controller returned HTTP {resp.status_code} authentication rejection.",
                )
            resp.raise_for_status()
            data = resp.json()
            return ControllerDispatchAck(
                controller_key=controller_key,
                ack_status=str(data.get("ack_status", "accepted")),
                device_sequence=data.get("device_sequence"),
                message=str(data.get("message", "Accepted by controller")),
                telemetry=data,
            )
        except httpx.TimeoutException:
            return ControllerDispatchAck(
                controller_key=controller_key,
                ack_status="timeout",
                device_sequence=None,
                message=f"HTTP timeout after {self.timeout_seconds}s reaching {controller_key}.",
            )
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            logger.warning(
                "CODEX HTTP command error on %s (%s)", controller_key, type(exc).__name__
            )
            return ControllerDispatchAck(
                controller_key=controller_key,
                ack_status="fault",
                device_sequence=None,
                message=f"HTTP transport error ({type(exc).__name__}).",
            )

    def dispatch_command(
        self,
        *,
        controller_key: str,
        endpoint_host: str | None,
        endpoint_port: int | None,
        command_payload: dict[str, Any],
        signed_headers: dict[str, str],
        uart_frame: bytes | None = None,
    ) -> ControllerDispatchAck:
        return self._post_command(
            controller_key=controller_key,
            endpoint_host=endpoint_host,
            endpoint_port=endpoint_port,
            path="/codex/command",
            command_payload=command_payload,
            signed_headers=signed_headers,
            uart_frame=uart_frame,
        )

    def dispatch_estop(
        self,
        *,
        controller_key: str,
        endpoint_host: str | None,
        endpoint_port: int | None,
        command_payload: dict[str, Any],
        signed_headers: dict[str, str],
        uart_frame: bytes | None = None,
    ) -> ControllerDispatchAck:
        return self._post_command(
            controller_key=controller_key,
            endpoint_host=endpoint_host,
            endpoint_port=endpoint_port,
            path="/codex/estop",
            command_payload=command_payload,
            signed_headers=signed_headers,
            uart_frame=uart_frame,
        )


_DEFAULT_MOCK_TRANSPORT = MockCodexTransport()


def get_codex_transport(mode: str | None = None) -> CodexTransport:
    """Resolve active CODEX transport implementation without hardcoding test mocks in prod."""
    selected = (mode or settings.CODEX_TRANSPORT_MODE).strip().lower()
    if selected == "mock":
        return _DEFAULT_MOCK_TRANSPORT
    if selected == "http":
        return HttpCodexTransport()
    raise ValueError(f"Unsupported CODEX_TRANSPORT_MODE '{selected}'. Expected 'mock' or 'http'.")
