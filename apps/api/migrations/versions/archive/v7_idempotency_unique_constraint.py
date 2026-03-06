"""V7: Add UNIQUE constraint on (source_vendor, idempotency_key) for idempotency enforcement.

Revision ID: v7
Revises: v6
Create Date: 2025-02-13

- Treats blank idempotency_key as invalid: updates '' to NULL before constraint.
- Verifies no duplicate (source_vendor, idempotency_key) where key is non-null and non-empty.
- Adds uq_transactions_source_vendor_idempotency_key. Does not modify other tables.
"""
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "v7"
down_revision: str | None = "v6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT_NAME = "uq_transactions_source_vendor_idempotency_key"


def upgrade() -> None:
    conn = op.get_bind()

    # 0) Drop v6 constraint if present (replaced by this migration)
    op.execute(
        "ALTER TABLE data_plane.transactions DROP CONSTRAINT IF EXISTS uq_source_idempotency"
    )

    # 1) Treat blank idempotency_key as invalid: update '' to NULL
    op.execute(
        """
        UPDATE data_plane.transactions
        SET idempotency_key = NULL
        WHERE idempotency_key = ''
        """
    )

    # 2) Verify no duplicate (source_vendor, idempotency_key) where idempotency_key is not null and not empty
    dupes = conn.execute(
        text("""
            SELECT source_vendor, idempotency_key, COUNT(*) AS cnt
            FROM data_plane.transactions
            WHERE source_vendor IS NOT NULL
              AND idempotency_key IS NOT NULL
              AND TRIM(idempotency_key) != ''
            GROUP BY source_vendor, idempotency_key
            HAVING COUNT(*) > 1
        """)
    ).fetchall()

    if dupes:
        dup_pairs = ", ".join(f"({r[0]!r}, {r[1]!r}) x{r[2]}" for r in dupes)
        raise RuntimeError(
            f"Migration v7 aborted: Duplicate (source_vendor, idempotency_key) pairs exist. "
            f"Resolve duplicates before applying {CONSTRAINT_NAME}. "
            f"Duplicates found: {dup_pairs}"
        )

    # 3) Add UNIQUE constraint
    op.execute(
        f"""
        ALTER TABLE data_plane.transactions
        ADD CONSTRAINT {CONSTRAINT_NAME} UNIQUE (source_vendor, idempotency_key)
        """
    )


def downgrade() -> None:
    op.execute(
        f"ALTER TABLE data_plane.transactions DROP CONSTRAINT IF EXISTS {CONSTRAINT_NAME}"
    )
