"""V1: Create control_plane and data_plane schemas and tables.

Revision ID: v1
Revises:
Create Date: 2025-02-12

"""
from collections.abc import Sequence

from alembic import op

revision: str = "v1"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS control_plane")
    op.execute("CREATE SCHEMA IF NOT EXISTS data_plane")

    op.execute("""
        CREATE TABLE IF NOT EXISTS control_plane.vendors (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_code TEXT UNIQUE,
            name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vendors_vendor_code "
        "ON control_plane.vendors(vendor_code)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vendors_created_at "
        "ON control_plane.vendors(created_at DESC)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS control_plane.operations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_operations_created_at "
        "ON control_plane.operations(created_at DESC)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS control_plane.vendor_endpoints (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_id UUID NOT NULL REFERENCES control_plane.vendors(id) ON DELETE CASCADE,
            endpoint_type TEXT NOT NULL,
            url TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vendor_endpoints_vendor_id "
        "ON control_plane.vendor_endpoints(vendor_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS control_plane.vendor_operation_allowlist (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_id UUID NOT NULL REFERENCES control_plane.vendors(id) ON DELETE CASCADE,
            operation_id UUID NOT NULL REFERENCES control_plane.operations(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE(vendor_id, operation_id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vendor_operation_allowlist_vendor_id "
        "ON control_plane.vendor_operation_allowlist(vendor_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS data_plane.transactions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            transaction_id TEXT NOT NULL,
            correlation_id TEXT NOT NULL,
            source_vendor TEXT NOT NULL,
            target_vendor TEXT NOT NULL,
            operation TEXT NOT NULL,
            idempotency_key TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute(
        "ALTER TABLE data_plane.transactions ADD COLUMN IF NOT EXISTS idempotency_key TEXT"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_transactions_correlation_id "
        "ON data_plane.transactions(correlation_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_transactions_idempotency_key "
        "ON data_plane.transactions(idempotency_key)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_transactions_created_at "
        "ON data_plane.transactions(created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_transactions_transaction_id "
        "ON data_plane.transactions(transaction_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS data_plane.audit_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            transaction_id TEXT NOT NULL,
            action TEXT NOT NULL,
            vendor_code TEXT,
            details JSONB,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_events_transaction_id "
        "ON data_plane.audit_events(transaction_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_events_vendor_code "
        "ON data_plane.audit_events(vendor_code)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_events_created_at "
        "ON data_plane.audit_events(created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS data_plane.audit_events")
    op.execute("DROP TABLE IF EXISTS data_plane.transactions")
    op.execute("DROP TABLE IF EXISTS control_plane.vendor_operation_allowlist")
    op.execute("DROP TABLE IF EXISTS control_plane.vendor_endpoints")
    op.execute("DROP TABLE IF EXISTS control_plane.operations")
    op.execute("DROP TABLE IF EXISTS control_plane.vendors")
    op.execute("DROP SCHEMA IF EXISTS data_plane")
    op.execute("DROP SCHEMA IF EXISTS control_plane")
