"""V6: Add UNIQUE constraint on (source_vendor, idempotency_key) for idempotency.

Revision ID: v6
Revises: v5
Create Date: 2025-02-13

Enforces idempotency at database level. Checks for duplicate (source_vendor, idempotency_key)
before applying; aborts with clear error if duplicates exist. Does not modify or drop data.
"""
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "v6"
down_revision: str | None = "v5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    # Check for duplicate (source_vendor, idempotency_key) where both are non-NULL
    dupes = conn.execute(
        text("""
            SELECT source_vendor, idempotency_key, COUNT(*) AS cnt
            FROM data_plane.transactions
            WHERE source_vendor IS NOT NULL AND idempotency_key IS NOT NULL
            GROUP BY source_vendor, idempotency_key
            HAVING COUNT(*) > 1
        """)
    ).fetchall()

    if dupes:
        dup_pairs = ", ".join(f"({r[0]!r}, {r[1]!r}) x{r[2]}" for r in dupes)
        raise RuntimeError(
            "Migration v6 aborted: Duplicate (source_vendor, idempotency_key) rows exist. "
            "Resolve duplicates before applying uq_source_idempotency. "
            f"Duplicates found: {dup_pairs}"
        )

    op.execute(
        "ALTER TABLE data_plane.transactions "
        "ADD CONSTRAINT uq_source_idempotency UNIQUE (source_vendor, idempotency_key)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE data_plane.transactions DROP CONSTRAINT IF EXISTS uq_source_idempotency"
    )
