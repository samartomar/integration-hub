"""V4: Add composite index for audit queries (vendorCode + created_at).

Supports: WHERE source_vendor = ? AND created_at range ORDER BY created_at DESC
Avoids full table scans.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v4"
down_revision: str | None = "v3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_transactions_audit_vendor_created "
        "ON data_plane.transactions(source_vendor, created_at DESC, transaction_id)"
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS data_plane.idx_transactions_audit_vendor_created"
    )
