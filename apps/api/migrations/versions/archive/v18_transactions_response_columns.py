"""V18: Add target_response_body and canonical_response_body to transactions.

Revision ID: v18
Revises: v17
Create Date: 2025-02-18

- target_response_body: raw response from target vendor
- canonical_response_body: canonical format after TO_CANONICAL_RESPONSE
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v18"
down_revision: str | None = "v17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE data_plane.transactions ADD COLUMN IF NOT EXISTS target_response_body JSONB"
    )
    op.execute(
        "ALTER TABLE data_plane.transactions ADD COLUMN IF NOT EXISTS canonical_response_body JSONB"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE data_plane.transactions DROP COLUMN IF EXISTS canonical_response_body"
    )
    op.execute(
        "ALTER TABLE data_plane.transactions DROP COLUMN IF EXISTS target_response_body"
    )
