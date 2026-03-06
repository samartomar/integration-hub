"""V3: Add is_active to vendors, response_body to transactions for idempotency.

Revision ID: v3
Revises: v2
Create Date: 2025-02-12
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v3"
down_revision: str | None = "v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE control_plane.vendors ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true"
    )
    op.execute(
        "ALTER TABLE data_plane.transactions ADD COLUMN IF NOT EXISTS response_body JSONB"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE control_plane.vendors DROP COLUMN IF EXISTS is_active")
    op.execute("ALTER TABLE data_plane.transactions DROP COLUMN IF EXISTS response_body")
