"""Allowlist change requests - dedicated table for allowlist approval flow.

Revision ID: v48
Revises: v47
Create Date: 2026-02-25

Dedicated table for allowlist-related change requests (ALLOWLIST_RULE, PROVIDER_NARROWING)
with normalized columns for source/target vendors, direction, and request metadata.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v48"
down_revision: str | None = "v47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_plane.allowlist_change_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_vendor_code TEXT NOT NULL,
            target_vendor_codes TEXT[],
            use_wildcard_target BOOLEAN NOT NULL DEFAULT false,
            operation_code TEXT NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('OUTBOUND', 'INBOUND')),
            rule_scope TEXT NOT NULL DEFAULT 'vendor',
            request_type TEXT NOT NULL CHECK (request_type IN ('ALLOWLIST_RULE', 'PROVIDER_NARROWING')),
            status TEXT NOT NULL DEFAULT 'PENDING'
                CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED')),
            requested_by TEXT,
            reviewed_by TEXT,
            decision_reason TEXT,
            raw_payload JSONB,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_allowlist_change_requests_status "
        "ON control_plane.allowlist_change_requests (status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_allowlist_change_requests_vendor_status "
        "ON control_plane.allowlist_change_requests (source_vendor_code, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_allowlist_change_requests_operation "
        "ON control_plane.allowlist_change_requests (operation_code)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS control_plane.allowlist_change_requests")
