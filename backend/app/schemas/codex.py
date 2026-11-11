"""Pydantic v2 request and response contracts for CODEX hardware subsystems and diagnostics."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class PublicControllerStatusOut(BaseModel):
    """Sanitized controller health entry exposed on public GET /api/v1/codex/status."""

    controller_key: str
    device_role: str
    board_model: str
    health_state: str
    verification_status: str
    heartbeat_fresh: bool
    uart_ok: bool
    driver_config_ok: bool
    led_controller_ok: bool
    estop_latched: bool
    battery_voltage_available: bool
    battery_voltage_v: float | None = None
    last_heartbeat_at: datetime | None = None


class PublicCodexStatusOut(BaseModel):
    """Non-sensitive subsystem readiness summary safe for public UI status pills."""

    transport_mode: str
    require_verified_bench: bool
    overall_status: str  # 'ready' | 'degraded_led_only' | 'not_ready' | 'estop_latched' | 'fault'
    motors_ready: bool
    led_ready: bool
    estop_latched: bool
    calibration_verified: bool
    led_mapping_verified: bool
    blockers: list[str] = Field(default_factory=list)
    controllers: list[PublicControllerStatusOut] = Field(default_factory=list)
    checked_at: datetime


class AdminHardwareDeviceOut(PublicControllerStatusOut):
    """Extended administrative diagnostic snapshot including host/port/firmware identity."""

    device_id: UUID
    endpoint_host: str | None = None
    endpoint_port: int | None = None
    transport_type: str
    expected_firmware_version: str | None = None
    reported_firmware_version: str | None = None
    reported_firmware_checksum: str | None = None
    last_handshake_at: datetime | None = None
    ping_latency_ms: float | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    device_metadata: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime


class AdminDevicesListOut(BaseModel):
    """Full three-controller diagnostic payload returned to hardware/system administrators."""

    transport_mode: str
    require_verified_bench: bool
    devices: list[AdminHardwareDeviceOut] = Field(default_factory=list)
    configurations: list[dict[str, Any]] = Field(default_factory=list)
    checked_at: datetime


class DeviceHeartbeatIn(BaseModel):
    """Heartbeat or probe refresh request for a CODEX controller."""

    probe_via_transport: bool = Field(
        default=True,
        description="If true, query configured transport; otherwise record pushed telemetry fields.",
    )
    reported_firmware_version: str | None = Field(default=None, max_length=64)
    reported_firmware_checksum: str | None = Field(default=None, max_length=64)
    expected_firmware_version: str | None = Field(default=None, max_length=64)
    verification_status: Literal["unverified", "bench_verified", "quarantined"] | None = None
    uart_ok: bool | None = None
    driver_config_ok: bool | None = None
    led_controller_ok: bool | None = None
    estop_latched: bool | None = None
    battery_voltage_available: bool | None = None
    battery_voltage_v: float | None = Field(default=None, ge=0.0, le=60.0)
    ping_latency_ms: float | None = Field(default=None, ge=0.0)
    last_error_code: str | None = Field(default=None, max_length=64)
    last_error_message: str | None = Field(default=None, max_length=500)
    reset_estop_latch: bool = False


class CalibrationCreateIn(BaseModel):
    """Create a versioned motor calibration profile (supersedes active axis without overwriting)."""

    controller_key: str = Field(default="motion_uno", min_length=2, max_length=50)
    motor_key: Literal["nema17", "byj"]
    motor_name: str = Field(..., min_length=2, max_length=100)
    motor_model: str | None = Field(default=None, max_length=100)
    driver_model: str | None = Field(default=None, max_length=100)
    gear_reduction_ratio: float = Field(..., gt=0.0, le=10000.0)
    full_steps_per_rev: int = Field(..., gt=0, le=10000)
    microsteps: int = Field(..., gt=0, le=256)
    direction_sign: Literal[1, -1] = 1
    max_step_rate: int = Field(..., gt=0, le=100000)
    acceleration: int = Field(..., gt=0, le=200000)
    backlash_steps: int = Field(default=0, ge=0, le=10000)
    zero_offset_deg: float = Field(default=0.0, ge=-360.0, le=360.0)
    travel_min_deg: float | None = None
    travel_max_deg: float | None = None
    calibration_version: str = Field(..., min_length=1, max_length=40)
    measured_by: str | None = Field(default=None, max_length=100)
    verification_status: Literal["unverified", "bench_verified", "deprecated"] = "unverified"
    calibration_notes: str | None = None
    activate: bool = True

    @field_validator("travel_max_deg")
    @classmethod
    def check_travel_bounds(cls, v: float | None, info: Any) -> float | None:
        t_min = info.data.get("travel_min_deg")
        if v is not None and t_min is not None and v <= t_min:
            raise ValueError("travel_max_deg must be strictly greater than travel_min_deg.")
        return v


class CalibrationUpdateIn(BaseModel):
    """Transition verification status or notes on an existing calibration profile cleanly."""

    calibration_id: int = Field(..., gt=0)
    verification_status: Literal["unverified", "bench_verified", "deprecated"]
    calibration_notes: str | None = None
    measured_by: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None


class CalibrationProfileOut(BaseModel):
    """Serialized motor calibration record."""

    calibration_id: int
    controller_key: str
    motor_key: str | None = None
    motor_name: str
    motor_model: str | None = None
    driver_model: str | None = None
    gear_reduction_ratio: float
    full_steps_per_rev: int
    microsteps: int
    direction_sign: int
    max_step_rate: int
    acceleration: int
    backlash_steps: int
    zero_offset_deg: float
    travel_min_deg: float | None = None
    travel_max_deg: float | None = None
    calibration_version: str
    measured_at: datetime | None = None
    measured_by: str | None = None
    verification_status: str
    calibration_notes: str | None = None
    supersedes_calibration_id: int | None = None
    is_active: bool


class MoonLedRegionUpsertIn(BaseModel):
    """Admin specification for 1 of the 13 Moon LED physical regions."""

    region_index: int = Field(..., ge=1, le=13)
    region_name: str = Field(..., min_length=2, max_length=120)
    centroid_lat: float | None = Field(default=None, ge=-90.0, le=90.0)
    centroid_lon: float | None = Field(default=None, ge=-180.0, le=180.0)
    boundary_polygon: Any | None = None
    pixel_indices: list[int] = Field(..., min_length=1)
    mapping_version: str = Field(default="v1.0", min_length=1, max_length=20)
    orientation_reference: str | None = Field(default="MOON_ME_PRIME_MERIDIAN_CENTER")
    verification_status: Literal[
        "unverified", "centroid_approximate", "bench_verified", "deprecated"
    ] = "unverified"
    geometry_source: str | None = Field(default="bench_measurement", max_length=100)
    output_channel: int | None = Field(default=0, ge=0, le=64)
    topology_mode: Literal["addressable_strip", "discrete_gpio", "matrix", "unverified"] = (
        "addressable_strip"
    )
    is_active: bool = True


class MoonLedRegionOut(BaseModel):
    """Serialized Moon LED region and physical LED channel pixels."""

    region_id: int
    region_index: int
    region_name: str
    centroid_lat: float | None = None
    centroid_lon: float | None = None
    boundary_polygon: Any | None = None
    pixel_indices: list[int] = Field(default_factory=list)
    mapping_version: str
    orientation_reference: str | None = None
    verification_status: str
    geometry_source: str | None = None
    is_active: bool
    normalized_pixels: list[dict[str, Any]] = Field(default_factory=list)


class CodexPreflightStepOut(BaseModel):
    """Single item in the 16-step CODEX pre-flight checklist."""

    step_number: int
    key: str
    passed: bool
    severity: Literal["ok", "warning", "blocker"]
    detail: str


class CodexRunPrepareIn(BaseModel):
    """Prepare a non-actuating CODEX payload derived from a completed simulation."""

    simulation_id: UUID
    execution_mode: Literal["full_codex", "led_only"] = "full_codex"
    physical_duration_seconds: int | None = Field(
        default=None,
        ge=5,
        le=300,
        description="Physical actuator move budget in seconds (separate from SPICE span).",
    )
    clamp_to_travel_limits: bool = False
    allow_unverified_preview: bool = Field(
        default=True,
        description="Allows dry-run calculation on unverified bench for review; never actuates.",
    )
    allow_centroid_led_fallback: bool = Field(
        default=False,
        description="Explicit opt-in for centroid-only LED estimation when polygons are absent.",
    )


class CodexRunPrepareOut(BaseModel):
    """Non-actuating prepared CODEX run plan and full 16-step pre-flight checklist."""

    hardware_run_id: UUID
    simulation_id: UUID
    site_id: int
    site_name: str
    execution_mode: str
    status: str
    ready_to_execute: bool
    simulation_duration_seconds: int
    playback_speed: float
    physical_duration_seconds: int
    kepler_reference: dict[str, Any]
    orbital_targets_deg: dict[str, Any]
    motor_plans: dict[str, Any] | None = None
    moon_led_plan: dict[str, Any] | None = None
    preflight_passed_count: int
    preflight_total_steps: int
    preflight_steps: list[CodexPreflightStepOut] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    actuation_performed: bool = False
    created_at: datetime | None = None


class CodexRunExecuteIn(BaseModel):
    """Explicit operator-confirmed execution request bound to a prepared run (or simulation)."""

    hardware_run_id: UUID
    confirmed: bool = Field(
        ..., description="Must be strictly True to authorize physical dispatch."
    )
    idempotency_key: str = Field(..., min_length=6, max_length=128)
    execution_mode: Literal["full_codex", "led_only"] | None = None


class ControllerAckOut(BaseModel):
    """Recorded per-controller acknowledgement detail."""

    controller_key: str
    ack_status: str
    device_sequence: int | None = None
    message: str | None = None
    received_at: datetime


class CodexRunStatusOut(BaseModel):
    """Execution status, signed command metadata, and per-device acks for a hardware run."""

    hardware_run_id: UUID
    simulation_id: UUID | None = None
    site_id: int | None = None
    status: str
    command_id: UUID | None = None
    calibration_version: str | None = None
    led_mapping_version: str | None = None
    configuration_version: str | None = None
    physical_duration_seconds: int | None = None
    operator_admin_id: UUID | None = None
    operator_confirmed_at: datetime | None = None
    idempotency_key: str | None = None
    failure_reason: str | None = None
    upload_started_at: datetime | None = None
    upload_acknowledged_at: datetime | None = None
    execution_started_at: datetime | None = None
    execution_finished_at: datetime | None = None
    estop_triggered_at: datetime | None = None
    prepared_payload: dict[str, Any] = Field(default_factory=dict)
    acknowledgements: list[ControllerAckOut] = Field(default_factory=list)


class CodexEventOut(BaseModel):
    """Single timeline event entry for a hardware run."""

    event_id: int
    controller_key: str | None = None
    event_type: str
    severity: str
    message: str | None = None
    payload: dict[str, Any] | None = None
    event_time: datetime


class CodexRunEventsOut(BaseModel):
    """List of hardware telemetry/lifecycle events for a run."""

    hardware_run_id: UUID
    status: str
    events: list[CodexEventOut] = Field(default_factory=list)


class CodexEstopIn(BaseModel):
    """High-priority operator emergency stop request."""

    reason: str = Field(default="Operator emergency stop triggered", min_length=3, max_length=300)
    hardware_run_id: UUID | None = None


class CodexEstopOut(BaseModel):
    """Emergency stop dispatch confirmation and aborted run/controller states."""

    estop_latched: bool
    triggered_at: datetime
    aborted_run_ids: list[UUID] = Field(default_factory=list)
    controller_acknowledgements: list[dict[str, Any]] = Field(default_factory=list)


class PlaceholderSpecIn(BaseModel):
    """Allow-listed template placeholder specification attached to a firmware version."""

    placeholder_key: str = Field(..., pattern=r"^[A-Z0-9_]{2,64}$")
    description: str = Field(..., min_length=2, max_length=300)
    data_type: Literal["int", "float", "bool", "string"]
    unit: str | None = Field(default=None, max_length=32)
    required: bool = True
    default_value: Any | None = None
    validation_schema: dict[str, Any] | None = None
    injection_format: Literal["cpp_literal", "int_flag", "c_identifier", "c_string"] = "cpp_literal"
    order_index: int = Field(default=0, ge=0)


class CodeVersionCreateIn(BaseModel):
    """Create a versioned firmware source snapshot with declared allow-listed placeholders."""

    controller_key: Literal["wifi_bridge", "motion_uno", "moon_led_s3"]
    version_label: str = Field(..., min_length=2, max_length=64)
    source_code: str = Field(..., min_length=10)
    language: str = Field(default="cpp", max_length=30)
    board_target: str = Field(..., min_length=2, max_length=50)
    library_manifest: dict[str, Any] | None = None
    notes: str | None = None
    placeholders: list[PlaceholderSpecIn] = Field(default_factory=list)
    activate: bool = True


class CodeVersionRenderIn(BaseModel):
    """Preview strictly allow-listed placeholder substitution for a firmware code version."""

    values: dict[str, Any] = Field(default_factory=dict)


class CodeVersionOut(BaseModel):
    """Serialized firmware version metadata + placeholder manifest."""

    code_version_id: UUID
    controller_key: str
    version_label: str
    language: str
    board_target: str
    checksum: str
    library_manifest: dict[str, Any] | None = None
    is_active: bool
    notes: str | None = None
    created_at: datetime
    placeholders: list[dict[str, Any]] = Field(default_factory=list)


class CodeVersionDetailOut(CodeVersionOut):
    """Detailed immutable firmware version including full source code and build logs."""

    source_code: str
    created_by_admin_id: UUID | None = None
    builds: list[dict[str, Any]] = Field(default_factory=list)


class CodeVersionDiffOut(BaseModel):
    """Unified source and placeholder comparison between two firmware versions."""

    base_version_id: UUID
    target_version_id: UUID
    controller_key: str
    base_version_label: str
    target_version_label: str
    unified_diff: str
    added_lines: int
    removed_lines: int
    placeholder_changes: list[dict[str, Any]] = Field(default_factory=list)


class CodeVersionSyntaxValidationOut(BaseModel):
    """Non-actuating static and placeholder validation result for a firmware version."""

    code_version_id: UUID
    controller_key: str
    board_target: str
    valid_static_checks: bool
    toolchain_available: bool
    toolchain_note: str
    undeclared_tokens: list[str] = Field(default_factory=list)
    malformed_tokens: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class HardwareVariableRefOut(BaseModel):
    """Live backend-driven variable reference entry for the split-pane Firmware Editor."""

    key: str
    category: str
    source_table: str
    description: str
    data_type: str
    unit: str | None = None
    current_value: Any | None = None
    injection_format: str
    example_placeholder: str


class HardwareConfigurationOut(BaseModel):
    """Serialized controller hardware baseline record."""

    hardware_config_id: UUID
    controller_key: str
    board_model: str
    firmware_target: str
    motor_type: str | None = None
    steps_per_revolution: int | None = None
    microstep_setting: int | None = None
    gear_ratio: float | None = None
    driver_model: str | None = None
    current_limit_setting: float | None = None
    led_count: int | None = None
    led_mapping_version: str | None = None
    config_json: dict[str, Any] | None = None
    is_active: bool
    updated_at: datetime


class HardwareRunAdminSummaryOut(BaseModel):
    """Administrative summary of a prepared or executed CODEX run."""

    hardware_run_id: UUID
    simulation_id: UUID | None = None
    site_id: int | None = None
    status: str
    start_time_utc: datetime
    duration_seconds: int
    physical_duration_seconds: int | None = None
    calibration_version: str | None = None
    led_mapping_version: str | None = None
    configuration_version: str | None = None
    operator_admin_id: UUID | None = None
    operator_confirmed_at: datetime | None = None
    execution_started_at: datetime | None = None
    execution_finished_at: datetime | None = None
    estop_triggered_at: datetime | None = None
    failure_reason: str | None = None
