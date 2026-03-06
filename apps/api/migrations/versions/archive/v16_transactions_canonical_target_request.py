"""V16: Add canonical_request and target_request to data_plane.transactions.

Revision ID: v16
Revises: v15
Create Date: 2025-02-18

- canonical_request: canonical payload after TO_CANONICAL mapping
- target_request: vendor-specific payload after FROM_CANONICAL mapping
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v16"
down_revision: str | None = "v15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE data_plane.transactions ADD COLUMN IF NOT EXISTS canonical_request JSONB"
    )
    op.execute(
        "ALTER TABLE data_plane.transactions ADD COLUMN IF NOT EXISTS target_request JSONB"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE data_plane.transactions DROP COLUMN IF EXISTS target_request"
    )
    op.execute(
        "ALTER TABLE data_plane.transactions DROP COLUMN IF EXISTS canonical_request"
    )
