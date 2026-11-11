"""Phase 7 Admin Portal RBAC alignment, admin password hygiene fields, and health components.

Revision ID: 007_phase7_admin_and_security
Revises: 006_codex_hardware_system
Create Date: 2026-11-11 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007_phase7_admin_and_security"
down_revision: str | None = "006_codex_hardware_system"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Additive credential hygiene columns on admins table
    op.add_column(
        "admins",
        sa.Column("password_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "admins",
        sa.Column(
            "password_must_rotate",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    conn = op.get_bind()

    # 2. Ensure full canonical + compatibility RBAC role dictionary exists idempotently
    conn.execute(
        sa.text(
            """
            INSERT INTO roles (role_key, description) VALUES
                ('super_admin', 'Unrestricted administrative access to all system modules, configurations, and users.'),
                ('system_admin', 'Can manage hardware infrastructure, system health diagnostics, and CODEX operational security.'),
                ('site_editor', 'Can create, update, and manage landing sites, research sections, pros/cons, and media assets.'),
                ('research_admin', 'Can stage, validate, preview, commit, and roll back scientific datasets and imports.'),
                ('hardware_admin', 'Can inspect device diagnostics, manage calibration profiles, LED mappings, and firmware versions.'),
                ('hardware_operator', 'Can operate CODEX hardware runs and trigger emergency stop procedures.'),
                ('viewer', 'Read-only access to administrative dashboards and preview content.')
            ON CONFLICT (role_key) DO NOTHING;
            """
        )
    )

    # 3. Seed baseline monitored system components for Admin System Health view
    conn.execute(
        sa.text(
            """
            INSERT INTO system_components (component_key, display_name, component_type, is_enabled) VALUES
                ('backend-api', 'FastAPI Core & Security Gateway', 'service', true),
                ('postgresql', 'PostgreSQL 18 Relational Database', 'database', true),
                ('spice-ephemeris', 'NAIF SPICE Ephemeris Engine (DE440 / MOON_ME)', 'scientific_engine', true),
                ('lola-dem', 'NASA PGDA LOLA Elevation Raster Assets', 'scientific_asset', true),
                ('ollama-ai', 'Local Ollama AI Assist Engine', 'ai_model', true),
                ('codex-hardware', 'CODEX Three-Controller Hardware Subsystem', 'hardware', true)
            ON CONFLICT (component_key) DO NOTHING;
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            DELETE FROM system_components
            WHERE component_key IN (
                'backend-api',
                'postgresql',
                'spice-ephemeris',
                'lola-dem',
                'ollama-ai',
                'codex-hardware'
            );
            """
        )
    )
    op.drop_column("admins", "password_must_rotate")
    op.drop_column("admins", "password_updated_at")
