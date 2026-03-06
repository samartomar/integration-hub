"""V19: Add canonical_request_body, target_request_body; standardize body column names.

Revision ID: v19
Revises: v18
Create Date: 2025-02-18

Adds nullable jsonb columns (IF NOT EXISTS, backwards compatible):
- canonical_request_body
- target_request_body

(v18 already added target_response_body, canonical_response_body)

Migrates data from canonical_request -> canonical_request_body,
target_request -> target_request_body for existing rows.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v19"
down_revision: str | None = "v18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE data_plane.transactions ADD COLUMN IF NOT EXISTS canonical_request_body JSONB"
    )
    op.execute(
        "ALTER TABLE data_plane.transactions ADD COLUMN IF NOT EXISTS target_request_body JSONB"
    )
    op.execute(
        """
        UPDATE data_plane.transactions
        SET canonical_request_body = canonical_request
        WHERE canonical_request_body IS NULL AND canonical_request IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE data_plane.transactions
        SET target_request_body = target_request
        WHERE target_request_body IS NULL AND target_request IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE data_plane.transactions DROP COLUMN IF EXISTS target_request_body"
    )
    op.execute(
        "ALTER TABLE data_plane.transactions DROP COLUMN IF EXISTS canonical_request_body"
    )
