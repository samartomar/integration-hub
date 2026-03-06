"""V14: Add idempotency uniqueness constraint - partial unique index ux_tx_source_idem.

Revision ID: v14
Revises: v13
Create Date: 2025-02-17

- Pre-migration cleanup: keep newest row per (source_vendor, idempotency_key),
  delete older duplicates; log how many deleted.
- Drops v10 partial index if present (uq_transactions_source_idempotency_partial).
- Creates partial unique index ux_tx_source_idem on (source_vendor, idempotency_key)
  WHERE source_vendor IS NOT NULL AND idempotency_key IS NOT NULL.

Enforces: two requests with same sourceVendor + idempotencyKey return replay,
no duplicate insert.
"""
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "v14"
down_revision: str | None = "v13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_INDEX_NAME = "uq_transactions_source_idempotency_partial"
NEW_INDEX_NAME = "ux_tx_source_idem"


def upgrade() -> None:
    conn = op.get_bind()

    # 1) Pre-migration cleanup: delete duplicate rows, keep newest per (source_vendor, idempotency_key)
    result = conn.execute(
        text("""
            WITH dupes AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY source_vendor, idempotency_key
                           ORDER BY created_at DESC NULLS LAST, id::text
                       ) AS rn
                FROM data_plane.transactions
                WHERE source_vendor IS NOT NULL
                  AND idempotency_key IS NOT NULL
                  AND TRIM(idempotency_key) != ''
            ),
            to_delete AS (
                SELECT id FROM dupes WHERE rn > 1
            )
            DELETE FROM data_plane.transactions
            WHERE id IN (SELECT id FROM to_delete)
            RETURNING id
        """)
    )
    deleted_rows = result.fetchall()
    deleted_count = len(deleted_rows)
    if deleted_count > 0:
        # Log via a simple print (migrations often run in CI; logging varies)
        print(f"Migration v14: Deleted {deleted_count} duplicate transaction row(s) (kept newest per source_vendor, idempotency_key)")

    # 2) Drop v10 index if present
    op.execute(f"DROP INDEX IF EXISTS data_plane.{OLD_INDEX_NAME}")

    # 3) Create new partial unique index
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {NEW_INDEX_NAME}
        ON data_plane.transactions (source_vendor, idempotency_key)
        WHERE source_vendor IS NOT NULL AND idempotency_key IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS data_plane.{NEW_INDEX_NAME}")

    # Restore v10-style partial index (idempotency_key only in WHERE)
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {OLD_INDEX_NAME}
        ON data_plane.transactions (source_vendor, idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )
