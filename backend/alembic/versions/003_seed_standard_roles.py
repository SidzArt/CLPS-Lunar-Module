"""Seed standard system RBAC roles.

Revision ID: 003_seed_standard_roles
Revises: 002_search_indexes
Create Date: 2026-11-11 04:15:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_seed_standard_roles"
down_revision: str | None = "002_search_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    roles_table = sa.table(
        "roles",
        sa.column("role_key", sa.String),
        sa.column("description", sa.Text),
    )

    op.bulk_insert(
        roles_table,
        [
            {
                "role_key": "super_admin",
                "description": "Unrestricted administrative access to all system modules, configurations, and users.",
            },
            {
                "role_key": "site_editor",
                "description": "Can create, update, and manage landing sites, research sections, pros/cons, and media assets.",
            },
            {
                "role_key": "research_admin",
                "description": "Can stage, validate, preview, commit, and roll back scientific datasets and imports.",
            },
            {
                "role_key": "hardware_operator",
                "description": "Can operate CODEX hardware simulations, upload firmware parameters, and control devices.",
            },
            {
                "role_key": "viewer",
                "description": "Read-only access to administrative dashboards and preview content.",
            },
        ],
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM roles WHERE role_key IN ('super_admin', 'site_editor', 'research_admin', 'hardware_operator', 'viewer');"
    )
