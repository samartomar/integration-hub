"""V8: REDRIVE FIX STEP 1 - Add request_body, parent_transaction_id, redrive_count to transactions.

Revision ID: v8
Revises: v7
Create Date: 2025-02-13

Adds columns for redrive tracking. No backfill of request_body. Does not modify existing statuses.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v8"
down_revision: str | None = "v7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add columns
    op.execute(
        "ALTER TABLE data_plane.transactions ADD COLUMN IF NOT EXISTS request_body JSONB"
    )
    op.execute(
        "ALTER TABLE data_plane.transactions ADD COLUMN IF NOT EXISTS parent_transaction_id UUID"
    )
    op.execute(
        "ALTER TABLE data_plane.transactions ADD COLUMN IF NOT EXISTS redrive_count INT NOT NULL DEFAULT 0"
    )

    # Add indexes
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_transactions_parent_transaction_id "
        "ON data_plane.transactions(parent_transaction_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_transactions_correlation_id "
        "ON data_plane.transactions(correlation_id)"
    )


def downgrade() -> None:
    # Drop indexes
    op.execute(
        "DROP INDEX IF EXISTS data_plane.idx_transactions_parent_transaction_id"
    )
    op.execute(
        "DROP INDEX IF EXISTS data_plane.idx_transactions_correlation_id"
    )

    # Drop columns
    op.execute(
        "ALTER TABLE data_plane.transactions DROP COLUMN IF EXISTS request_body"
    )
    op.execute(
        "ALTER TABLE data_plane.transactions DROP COLUMN IF EXISTS parent_transaction_id"
    )
    op.execute(
        "ALTER TABLE data_plane.transactions DROP COLUMN IF EXISTS redrive_count"
    )
