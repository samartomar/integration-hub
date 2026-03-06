"""V28: Transaction performance indexes for Admin & Vendor dashboards.

Adds composite btree indexes for:
- Admin list by vendor over time: (source_vendor, created_at DESC) - v4 already has
    idx_transactions_audit_vendor_created (source_vendor, created_at DESC, transaction_id)
- Vendor outbound: source_vendor + created_at
- Vendor inbound: target_vendor + created_at

Benefits:
- GET /v1/audit/transactions (vendorCode): idx_transactions_audit_vendor_created
- GET /v1/vendor/transactions direction=outbound: idx_transactions_source_vendor_created_at
- GET /v1/vendor/transactions direction=inbound: idx_transactions_target_vendor_created_at
- GET /v1/vendor/transactions direction=all: both indexes via bitmap OR
- GET /v1/vendor/metrics/overview: both indexes for (source=X OR target=X) AND created_at BETWEEN

No redundant indexes dropped - idx_transactions_created_at kept for admin list without vendorCode.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v28"
down_revision: str | None = "v27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Vendor outbound: WHERE source_vendor = ? AND created_at BETWEEN ... ORDER BY created_at DESC
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_transactions_source_vendor_created_at "
        "ON data_plane.transactions (source_vendor, created_at DESC)"
    )
    # Vendor inbound: WHERE target_vendor = ? AND created_at BETWEEN ... ORDER BY created_at DESC
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_transactions_target_vendor_created_at "
        "ON data_plane.transactions (target_vendor, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS data_plane.idx_transactions_source_vendor_created_at")
    op.execute("DROP INDEX IF EXISTS data_plane.idx_transactions_target_vendor_created_at")
