"""Admin change requests - gate vendor config changes behind approval.

Revision ID: v46
Revises: baseline
Create Date: 2026-02-24

"""
from collections.abc import Sequence

from alembic import op

revision: str = "v46"
down_revision: str | None = "baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_plane.change_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            request_type TEXT NOT NULL,
            vendor_code TEXT NOT NULL,
            operation_code TEXT,
            payload JSONB NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING'
                CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'APPLIED', 'CANCELLED')),
            requested_by TEXT,
            requested_via TEXT,
            approved_by TEXT,
            approved_at TIMESTAMPTZ,
            rejected_reason TEXT,
            applied_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_change_requests_vendor_status "
        "ON control_plane.change_requests (vendor_code, status, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_change_requests_type_status "
        "ON control_plane.change_requests (request_type, status, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS control_plane.change_requests")
