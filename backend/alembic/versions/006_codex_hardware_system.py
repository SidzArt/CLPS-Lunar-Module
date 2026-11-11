"""Phase 5 CODEX hardware registry, replay/ack ledgers, calibration/LED versioning, and Phase 2-4 data hygiene.

Revision ID: 006_codex_hardware_system
Revises: 005_simulation_engine
Create Date: 2026-11-11 11:42:00
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "006_codex_hardware_system"
down_revision: str | None = "005_simulation_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create hardware_devices registry table
    op.create_table(
        "hardware_devices",
        sa.Column("device_id", sa.UUID(), nullable=False),
        sa.Column("controller_key", sa.String(length=50), nullable=False),
        sa.Column("device_role", sa.String(length=50), nullable=False),
        sa.Column("board_model", sa.String(length=100), nullable=False),
        sa.Column("endpoint_host", sa.String(length=128), nullable=True),
        sa.Column("endpoint_port", sa.Integer(), nullable=True),
        sa.Column("transport_type", sa.String(length=30), nullable=False, server_default="http"),
        sa.Column("health_state", sa.String(length=40), nullable=False, server_default="offline"),
        sa.Column(
            "verification_status", sa.String(length=30), nullable=False, server_default="unverified"
        ),
        sa.Column("expected_firmware_version", sa.String(length=64), nullable=True),
        sa.Column("reported_firmware_version", sa.String(length=64), nullable=True),
        sa.Column("reported_firmware_checksum", sa.String(length=64), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_handshake_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ping_latency_ms", sa.Float(), nullable=True),
        sa.Column("uart_ok", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "driver_config_ok", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "led_controller_ok", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("estop_latched", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "battery_voltage_available",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("battery_voltage_v", sa.Float(), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("device_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "health_state IN ('offline', 'online_unverified', 'ready', 'busy', 'completed', "
            "'fault', 'firmware_mismatch', 'calibration_missing', 'configuration_mismatch')",
            name="check_hardware_device_health_state",
        ),
        sa.CheckConstraint(
            "verification_status IN ('unverified', 'bench_verified', 'quarantined')",
            name="check_hardware_device_verification_status",
        ),
        sa.PrimaryKeyConstraint("device_id"),
    )
    op.create_index(
        op.f("ix_hardware_devices_controller_key"),
        "hardware_devices",
        ["controller_key"],
        unique=True,
    )
    op.create_index(
        op.f("ix_hardware_devices_health_state"),
        "hardware_devices",
        ["health_state"],
        unique=False,
    )

    # 2. Create normalized moon_led_region_pixels table
    op.create_table(
        "moon_led_region_pixels",
        sa.Column("mapping_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("region_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "controller_key", sa.String(length=50), nullable=False, server_default="moon_led_s3"
        ),
        sa.Column("mapping_version", sa.String(length=20), nullable=False, server_default="v1.0"),
        sa.Column("output_channel", sa.Integer(), nullable=True),
        sa.Column("pixel_index", sa.Integer(), nullable=False),
        sa.Column("pixel_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "topology_mode", sa.String(length=40), nullable=False, server_default="unverified"
        ),
        sa.Column(
            "verification_status", sa.String(length=30), nullable=False, server_default="unverified"
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["region_id"], ["moon_led_regions.region_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("mapping_id"),
    )
    op.create_index(
        op.f("ix_moon_led_region_pixels_region_id"),
        "moon_led_region_pixels",
        ["region_id"],
        unique=False,
    )

    # 3. Create codex_command_nonces table (replay/TTL/idempotency protection)
    op.create_table(
        "codex_command_nonces",
        sa.Column("command_id", sa.UUID(), nullable=False),
        sa.Column("hardware_run_id", sa.UUID(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("nonce", sa.String(length=128), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("target_devices", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("issued_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="issued"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('issued', 'dispatched', 'acknowledged', 'completed', 'faulted', 'expired', 'aborted')",
            name="check_codex_command_status",
        ),
        sa.ForeignKeyConstraint(
            ["hardware_run_id"], ["hardware_runs.hardware_run_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("command_id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("nonce"),
    )
    op.create_index(
        op.f("ix_codex_command_nonces_hardware_run_id"),
        "codex_command_nonces",
        ["hardware_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_codex_command_nonces_status"),
        "codex_command_nonces",
        ["status"],
        unique=False,
    )

    # 4. Create hardware_command_acknowledgements table (per-device ack records)
    op.create_table(
        "hardware_command_acknowledgements",
        sa.Column("ack_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("hardware_run_id", sa.UUID(), nullable=False),
        sa.Column("command_id", sa.UUID(), nullable=False),
        sa.Column("controller_key", sa.String(length=50), nullable=False),
        sa.Column("ack_status", sa.String(length=40), nullable=False),
        sa.Column("device_sequence", sa.BigInteger(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("telemetry", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "ack_status IN ('accepted', 'started', 'completed', 'rejected', 'fault', 'timeout', 'estopped')",
            name="check_hardware_ack_status",
        ),
        sa.ForeignKeyConstraint(
            ["hardware_run_id"], ["hardware_runs.hardware_run_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("ack_id"),
    )
    op.create_index(
        op.f("ix_hardware_command_acknowledgements_command_id"),
        "hardware_command_acknowledgements",
        ["command_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_hardware_command_acknowledgements_controller_key"),
        "hardware_command_acknowledgements",
        ["controller_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_hardware_command_acknowledgements_hardware_run_id"),
        "hardware_command_acknowledgements",
        ["hardware_run_id"],
        unique=False,
    )

    # 5. Extend hardware_runs additively
    op.add_column("hardware_runs", sa.Column("command_id", sa.UUID(), nullable=True))
    op.add_column(
        "hardware_runs", sa.Column("calibration_version", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "hardware_runs", sa.Column("led_mapping_version", sa.String(length=30), nullable=True)
    )
    op.add_column(
        "hardware_runs", sa.Column("configuration_version", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "hardware_runs", sa.Column("physical_duration_seconds", sa.Integer(), nullable=True)
    )
    op.add_column("hardware_runs", sa.Column("operator_admin_id", sa.UUID(), nullable=True))
    op.add_column(
        "hardware_runs",
        sa.Column("operator_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "hardware_runs", sa.Column("idempotency_key", sa.String(length=128), nullable=True)
    )
    op.add_column(
        "hardware_runs", sa.Column("estop_triggered_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        op.f("ix_hardware_runs_command_id"), "hardware_runs", ["command_id"], unique=False
    )
    op.create_unique_constraint(
        "uq_hardware_runs_idempotency_key", "hardware_runs", ["idempotency_key"]
    )
    op.create_foreign_key(
        "fk_hardware_runs_operator_admin",
        "hardware_runs",
        "admins",
        ["operator_admin_id"],
        ["admin_id"],
        ondelete="SET NULL",
    )

    # 6. Extend moon_led_regions additively
    op.add_column(
        "moon_led_regions",
        sa.Column("orientation_reference", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "moon_led_regions",
        sa.Column(
            "verification_status", sa.String(length=30), nullable=False, server_default="unverified"
        ),
    )
    op.add_column(
        "moon_led_regions", sa.Column("geometry_source", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "moon_led_regions",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "check_moon_led_verification_status",
        "moon_led_regions",
        "verification_status IN ('unverified', 'centroid_approximate', 'bench_verified', 'deprecated')",
    )

    # 7. Extend motor_calibration_profiles additively
    op.add_column(
        "motor_calibration_profiles",
        sa.Column("motor_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "motor_calibration_profiles",
        sa.Column("motor_model", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "motor_calibration_profiles",
        sa.Column("driver_model", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "motor_calibration_profiles",
        sa.Column("direction_sign", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "motor_calibration_profiles",
        sa.Column(
            "calibration_version",
            sa.String(length=40),
            nullable=False,
            server_default="v1.0-unverified",
        ),
    )
    op.add_column(
        "motor_calibration_profiles",
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "motor_calibration_profiles",
        sa.Column("measured_by", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "motor_calibration_profiles",
        sa.Column(
            "verification_status", sa.String(length=30), nullable=False, server_default="unverified"
        ),
    )
    op.add_column(
        "motor_calibration_profiles",
        sa.Column("calibration_notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "motor_calibration_profiles",
        sa.Column("supersedes_calibration_id", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        op.f("ix_motor_calibration_profiles_motor_key"),
        "motor_calibration_profiles",
        ["motor_key"],
        unique=False,
    )
    op.create_check_constraint(
        "check_motor_direction_sign",
        "motor_calibration_profiles",
        "direction_sign IN (1, -1)",
    )
    op.create_check_constraint(
        "check_motor_verification_status",
        "motor_calibration_profiles",
        "verification_status IN ('unverified', 'bench_verified', 'deprecated')",
    )
    op.create_foreign_key(
        "fk_motor_calibrations_supersedes",
        "motor_calibration_profiles",
        "motor_calibration_profiles",
        ["supersedes_calibration_id"],
        ["calibration_id"],
        ondelete="SET NULL",
    )

    # 8. Seed RBAC roles aligned with PDF spec and standard operational roles
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO roles (role_key, description) VALUES
                ('hardware_admin', 'Can inspect device diagnostics, manage calibration profiles, LED mappings, and firmware versions.'),
                ('system_admin', 'Can manage hardware infrastructure, system health diagnostics, and CODEX operational security.')
            ON CONFLICT (role_key) DO NOTHING;
            """
        )
    )

    # 9. Non-destructive Phase 2-4 data hygiene & provenance reconciliation
    conn.execute(
        sa.text(
            """
            UPDATE landing_sites
            SET catalogue_status = 'archived'
            WHERE site_code = 'CLPS-TEST-001' AND catalogue_status != 'archived';
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE site_metrics
            SET data_quality_status = 'unverified'
            WHERE source_id IS NULL AND data_quality_status = 'verified';
            """
        )
    )

    # 10. Seed the 3 physical CODEX controllers in unverified/offline initial baseline
    seed_devices = [
        {
            "device_id": str(uuid.uuid4()),
            "controller_key": "wifi_bridge",
            "device_role": "bridge",
            "board_model": "ESP32",
            "endpoint_host": "192.168.1.101",
            "endpoint_port": 80,
            "transport_type": "http",
            "health_state": "offline",
            "verification_status": "unverified",
            "device_metadata": {
                "notes": "Ordinary ESP32 HTTP-to-UART bridge; awaits bench flashing and HMAC provisioning"
            },
        },
        {
            "device_id": str(uuid.uuid4()),
            "controller_key": "motion_uno",
            "device_role": "motion_controller",
            "board_model": "Arduino Uno R3",
            "endpoint_host": "UART0",
            "endpoint_port": None,
            "transport_type": "uart_via_bridge",
            "health_state": "offline",
            "verification_status": "unverified",
            "device_metadata": {
                "notes": "5V logic; requires verified level shifter on ESP32 UART and physical E-stop before energizing motors"
            },
        },
        {
            "device_id": str(uuid.uuid4()),
            "controller_key": "moon_led_s3",
            "device_role": "led_controller",
            "board_model": "ESP32-S3",
            "endpoint_host": "192.168.1.102",
            "endpoint_port": 80,
            "transport_type": "http",
            "health_state": "offline",
            "verification_status": "unverified",
            "device_metadata": {
                "notes": "13-region Moon LED controller; LED topology and battery ADC circuit unverified"
            },
        },
    ]
    for dev in seed_devices:
        conn.execute(
            sa.text(
                """
                INSERT INTO hardware_devices (
                    device_id, controller_key, device_role, board_model,
                    endpoint_host, endpoint_port, transport_type,
                    health_state, verification_status,
                    uart_ok, driver_config_ok, led_controller_ok,
                    estop_latched, battery_voltage_available, battery_voltage_v,
                    device_metadata
                ) VALUES (
                    CAST(:device_id AS UUID), :controller_key, :device_role, :board_model,
                    :endpoint_host, :endpoint_port, :transport_type,
                    :health_state, :verification_status,
                    false, false, false,
                    false, false, NULL,
                    CAST(:device_metadata AS JSONB)
                )
                ON CONFLICT (controller_key) DO NOTHING;
                """
            ),
            {
                **dev,
                "device_metadata": json.dumps(dev["device_metadata"]),
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM roles WHERE role_key IN ('hardware_admin', 'system_admin');"))

    op.drop_constraint(
        "fk_motor_calibrations_supersedes", "motor_calibration_profiles", type_="foreignkey"
    )
    op.drop_constraint(
        "check_motor_verification_status", "motor_calibration_profiles", type_="check"
    )
    op.drop_constraint("check_motor_direction_sign", "motor_calibration_profiles", type_="check")
    op.drop_index(
        op.f("ix_motor_calibration_profiles_motor_key"), table_name="motor_calibration_profiles"
    )
    for col in (
        "supersedes_calibration_id",
        "calibration_notes",
        "verification_status",
        "measured_by",
        "measured_at",
        "calibration_version",
        "direction_sign",
        "driver_model",
        "motor_model",
        "motor_key",
    ):
        op.drop_column("motor_calibration_profiles", col)

    op.drop_constraint("check_moon_led_verification_status", "moon_led_regions", type_="check")
    for col in ("updated_at", "geometry_source", "verification_status", "orientation_reference"):
        op.drop_column("moon_led_regions", col)

    op.drop_constraint("fk_hardware_runs_operator_admin", "hardware_runs", type_="foreignkey")
    op.drop_constraint("uq_hardware_runs_idempotency_key", "hardware_runs", type_="unique")
    op.drop_index(op.f("ix_hardware_runs_command_id"), table_name="hardware_runs")
    for col in (
        "estop_triggered_at",
        "idempotency_key",
        "operator_confirmed_at",
        "operator_admin_id",
        "physical_duration_seconds",
        "configuration_version",
        "led_mapping_version",
        "calibration_version",
        "command_id",
    ):
        op.drop_column("hardware_runs", col)

    op.drop_index(
        op.f("ix_hardware_command_acknowledgements_hardware_run_id"),
        table_name="hardware_command_acknowledgements",
    )
    op.drop_index(
        op.f("ix_hardware_command_acknowledgements_controller_key"),
        table_name="hardware_command_acknowledgements",
    )
    op.drop_index(
        op.f("ix_hardware_command_acknowledgements_command_id"),
        table_name="hardware_command_acknowledgements",
    )
    op.drop_table("hardware_command_acknowledgements")

    op.drop_index(op.f("ix_codex_command_nonces_status"), table_name="codex_command_nonces")
    op.drop_index(
        op.f("ix_codex_command_nonces_hardware_run_id"), table_name="codex_command_nonces"
    )
    op.drop_table("codex_command_nonces")

    op.drop_index(op.f("ix_moon_led_region_pixels_region_id"), table_name="moon_led_region_pixels")
    op.drop_table("moon_led_region_pixels")

    op.drop_index(op.f("ix_hardware_devices_health_state"), table_name="hardware_devices")
    op.drop_index(op.f("ix_hardware_devices_controller_key"), table_name="hardware_devices")
    op.drop_table("hardware_devices")
