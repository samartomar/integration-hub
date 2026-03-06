"""V10: Replace idempotency unique constraint with partial unique index.

Revision ID: v10
Revises: v9
Create Date: 2025-02-13

- Drops v7 UNIQUE constraint uq_transactions_source_vendor_idempotency_key.
- Creates partial unique index on (source_vendor, idempotency_key)
  WHERE idempotency_key IS NOT NULL.

This allows multiple rows with idempotency_key=NULL (e.g. validation_failed)
while enforcing uniqueness when key is present. Race-safe: concurrent inserts
with same key will raise unique_violation; handler catches and returns replay.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v10"
down_revision: str | None = "v9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT_NAME = "uq_transactions_source_vendor_idempotency_key"
INDEX_NAME = "uq_transactions_source_idempotency_partial"


def upgrade() -> None:
    # 1) Drop v7 UNIQUE constraint (may not exist if v7 was never applied)
    op.execute(
        f"ALTER TABLE data_plane.transactions DROP CONSTRAINT IF EXISTS {CONSTRAINT_NAME}"
    )

    # 2) Create partial unique index
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME}
        ON data_plane.transactions (source_vendor, idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS data_plane.{INDEX_NAME}")

    # Restore v7-style full constraint (requires no duplicate non-null keys)
    op.execute(
        f"""
        ALTER TABLE data_plane.transactions
        ADD CONSTRAINT {CONSTRAINT_NAME} UNIQUE (source_vendor, idempotency_key)
        """
    )
