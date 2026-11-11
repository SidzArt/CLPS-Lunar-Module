"""SQLAlchemy models for CODEX hardware, firmware versions, calibration, and runs."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    UUID,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HardwareConfiguration(Base):
    """Controller hardware parameters, stepper pin configurations, and motor ratings."""

    __tablename__ = "hardware_configurations"

    hardware_config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    controller_key: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # 'wifi_bridge', 'motion_uno', 'moon_led_s3'
    board_model: Mapped[str] = mapped_column(String(100), nullable=False)
    firmware_target: Mapped[str] = mapped_column(String(100), nullable=False)
    motor_type: Mapped[str | None] = mapped_column(String(100))
    steps_per_revolution: Mapped[int | None] = mapped_column(Integer)
    microstep_setting: Mapped[int | None] = mapped_column(Integer)
    gear_ratio: Mapped[float | None] = mapped_column(Float)
    driver_model: Mapped[str | None] = mapped_column(String(100))
    current_limit_setting: Mapped[float | None] = mapped_column(Float)
    led_count: Mapped[int | None] = mapped_column(Integer)
    led_mapping_version: Mapped[str | None] = mapped_column(String(50))
    config_json: Mapped[dict | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class HardwareCodeVersion(Base):
    """Immutable full source code version for microcontrollers (C/C++ sketches)."""

    __tablename__ = "hardware_code_versions"

    code_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    controller_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    version_label: Mapped[str] = mapped_column(String(100), nullable=False)
    source_code: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(50), default="cpp")
    board_target: Mapped[str] = mapped_column(String(100), nullable=False)
    library_manifest: Mapped[dict | None] = mapped_column(JSONB)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)


class CodePlaceholder(Base):
    """Registered placeholder token for runtime variable injection (e.g. {{NEMA17_STEP_COUNT}})."""

    __tablename__ = "code_placeholders"

    placeholder_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hardware_code_versions.code_version_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    placeholder_key: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    data_type: Mapped[str] = mapped_column(String(50), default="integer")
    unit: Mapped[str | None] = mapped_column(String(50))
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    default_value: Mapped[dict | None] = mapped_column(JSONB)
    validation_schema: Mapped[dict | None] = mapped_column(JSONB)
    injection_format: Mapped[str | None] = mapped_column(String(100))
    order_index: Mapped[int] = mapped_column(Integer, default=0)


class HardwareRun(Base):
    """Telemetry and execution trace of a physical demonstration run."""

    __tablename__ = "hardware_runs"

    hardware_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    simulation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("simulation_runs.simulation_id", ondelete="SET NULL"),
        index=True,
    )
    site_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("landing_sites.site_id", ondelete="SET NULL"), index=True
    )
    start_time_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(BigInteger, nullable=False)
    prepared_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    code_version_ids: Mapped[dict | None] = mapped_column(JSONB)
    hardware_config_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(50), default="prepared", index=True)
    upload_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    upload_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    command_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    calibration_version: Mapped[str | None] = mapped_column(String(64))
    led_mapping_version: Mapped[str | None] = mapped_column(String(30))
    configuration_version: Mapped[str | None] = mapped_column(String(64))
    physical_duration_seconds: Mapped[int | None] = mapped_column(Integer)
    operator_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admins.admin_id", ondelete="SET NULL")
    )
    operator_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    estop_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HardwareEvent(Base):
    """Structured telemetry, heartbeat, or error event received from controllers."""

    __tablename__ = "hardware_events"

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    hardware_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hardware_runs.hardware_run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    controller_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_time: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    payload: Mapped[dict | None] = mapped_column(JSONB)
    message: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), default="INFO")


class MoonLedRegion(Base):
    """Calibrated spherical partition zone mapping lunar coordinates to physical Moon LEDs."""

    __tablename__ = "moon_led_regions"

    region_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    region_index: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    region_name: Mapped[str] = mapped_column(String(100), nullable=False)
    centroid_lat: Mapped[float] = mapped_column(Numeric(10, 7), nullable=False)
    centroid_lon: Mapped[float] = mapped_column(Numeric(10, 7), nullable=False)
    boundary_polygon: Mapped[dict | None] = mapped_column(JSONB)
    pixel_indices: Mapped[list] = mapped_column(ARRAY(Integer), nullable=False)
    mapping_version: Mapped[str] = mapped_column(String(20), default="v1.0")
    orientation_reference: Mapped[str | None] = mapped_column(String(100))
    verification_status: Mapped[str] = mapped_column(String(30), default="unverified")
    geometry_source: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("region_index BETWEEN 1 AND 13", name="check_moon_led_region_index"),
        CheckConstraint(
            "verification_status IN ('unverified', 'centroid_approximate', 'bench_verified', 'deprecated')",
            name="check_moon_led_verification_status",
        ),
    )


class MotorCalibrationProfile(Base):
    """Measured kinematic conversion constants for physical stepper motors and linkages."""

    __tablename__ = "motor_calibration_profiles"

    calibration_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    controller_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    motor_key: Mapped[str | None] = mapped_column(String(64), index=True)
    motor_name: Mapped[str] = mapped_column(String(100), nullable=False)
    motor_model: Mapped[str | None] = mapped_column(String(100))
    driver_model: Mapped[str | None] = mapped_column(String(100))
    gear_reduction_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    full_steps_per_rev: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    microsteps: Mapped[int] = mapped_column(Integer, nullable=False, default=16)
    direction_sign: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_step_rate: Mapped[int] = mapped_column(Integer, nullable=False, default=2000)
    acceleration: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    backlash_steps: Mapped[int] = mapped_column(Integer, default=0)
    zero_offset_deg: Mapped[float] = mapped_column(Float, default=0.0)
    travel_min_deg: Mapped[float | None] = mapped_column(Float)
    travel_max_deg: Mapped[float | None] = mapped_column(Float)
    calibration_date: Mapped[date | None] = mapped_column(Date)
    calibration_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="v1.0-unverified"
    )
    measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    measured_by: Mapped[str | None] = mapped_column(String(100))
    verification_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unverified"
    )
    calibration_notes: Mapped[str | None] = mapped_column(Text)
    supersedes_calibration_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("motor_calibration_profiles.calibration_id", ondelete="SET NULL"),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        CheckConstraint("direction_sign IN (1, -1)", name="check_motor_direction_sign"),
        CheckConstraint(
            "verification_status IN ('unverified', 'bench_verified', 'deprecated')",
            name="check_motor_verification_status",
        ),
    )


class HardwareDevice(Base):
    """Independent live health and firmware registry for CODEX physical controllers."""

    __tablename__ = "hardware_devices"

    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    controller_key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    device_role: Mapped[str] = mapped_column(String(50), nullable=False)
    board_model: Mapped[str] = mapped_column(String(100), nullable=False)
    endpoint_host: Mapped[str | None] = mapped_column(String(128))
    endpoint_port: Mapped[int | None] = mapped_column(Integer)
    transport_type: Mapped[str] = mapped_column(String(30), nullable=False, default="http")
    health_state: Mapped[str] = mapped_column(
        String(40), nullable=False, default="offline", index=True
    )
    verification_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unverified"
    )
    expected_firmware_version: Mapped[str | None] = mapped_column(String(64))
    reported_firmware_version: Mapped[str | None] = mapped_column(String(64))
    reported_firmware_checksum: Mapped[str | None] = mapped_column(String(64))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_handshake_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ping_latency_ms: Mapped[float | None] = mapped_column(Float)
    uart_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    driver_config_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    led_controller_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    estop_latched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    battery_voltage_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    battery_voltage_v: Mapped[float | None] = mapped_column(Float)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    device_metadata: Mapped[dict | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "health_state IN ('offline', 'online_unverified', 'ready', 'busy', 'completed', "
            "'fault', 'firmware_mismatch', 'calibration_missing', 'configuration_mismatch')",
            name="check_hardware_device_health_state",
        ),
        CheckConstraint(
            "verification_status IN ('unverified', 'bench_verified', 'quarantined')",
            name="check_hardware_device_verification_status",
        ),
    )


class MoonLedRegionPixel(Base):
    """Normalized physical LED/GPIO channel mapping for each lunar region (1-13)."""

    __tablename__ = "moon_led_region_pixels"

    mapping_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    region_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("moon_led_regions.region_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    controller_key: Mapped[str] = mapped_column(String(50), nullable=False, default="moon_led_s3")
    mapping_version: Mapped[str] = mapped_column(String(20), nullable=False, default="v1.0")
    output_channel: Mapped[int | None] = mapped_column(Integer)
    pixel_index: Mapped[int] = mapped_column(Integer, nullable=False)
    pixel_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    topology_mode: Mapped[str] = mapped_column(String(40), nullable=False, default="unverified")
    verification_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unverified"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CodexCommandNonce(Base):
    """Replay-protection, TTL, sequence tracking, and idempotency ledger for CODEX commands."""

    __tablename__ = "codex_command_nonces"

    command_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    hardware_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hardware_runs.hardware_run_id", ondelete="CASCADE"),
        index=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    nonce: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_devices: Mapped[list] = mapped_column(JSONB, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    issued_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="issued", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "status IN ('issued', 'dispatched', 'acknowledged', 'completed', 'faulted', 'expired', 'aborted')",
            name="check_codex_command_status",
        ),
    )


class HardwareCommandAcknowledgement(Base):
    """Independent per-controller acknowledgement record for dispatched CODEX commands."""

    __tablename__ = "hardware_command_acknowledgements"

    ack_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    hardware_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hardware_runs.hardware_run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    command_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    controller_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    ack_status: Mapped[str] = mapped_column(String(40), nullable=False)
    device_sequence: Mapped[int | None] = mapped_column(BigInteger)
    message: Mapped[str | None] = mapped_column(Text)
    telemetry: Mapped[dict | None] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "ack_status IN ('accepted', 'started', 'completed', 'rejected', 'fault', 'timeout', 'estopped')",
            name="check_hardware_ack_status",
        ),
    )
