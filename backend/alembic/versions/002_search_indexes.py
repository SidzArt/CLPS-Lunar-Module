"""Add full-text search and trigram indexes for catalogue exploration.

Revision ID: 002_search_indexes
Revises: 356b56f822c2
Create Date: 2026-11-11 04:05:00
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_search_indexes"
down_revision: str | None = "356b56f822c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Ensure pg_trgm extension is available for tolerant text search
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    # Full-text search GIN index on long-form research body
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_site_content_fts ON site_content "
        "USING gin (to_tsvector('english', body));"
    )

    # Trigram index on landing site display names for fast prefix/typo search
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_landing_sites_name_trgm ON landing_sites "
        "USING gin (site_name gin_trgm_ops);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_site_content_fts;")
    op.execute("DROP INDEX IF EXISTS idx_landing_sites_name_trgm;")
