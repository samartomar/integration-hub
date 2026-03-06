"""Vendor change requests - minimal approval flow (Vendor + Admin gated).

Revision ID: v47
Revises: v46
Create Date: 2026-02-24

"""
from collections.abc import Sequence

from alembic import op

revision: str = "v47"
down_revision: str | None = "v46"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE control_plane.vendor_change_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

            requesting_vendor_code TEXT NOT NULL,
            requested_by TEXT,

            request_type TEXT NOT NULL
                CHECK (request_type IN ('ALLOWLIST_RULE', 'ENDPOINT_CONFIG', 'MAPPING_CONFIG', 'VENDOR_CONTRACT_CHANGE')),
            target_vendor_code TEXT,
            operation_code TEXT,
            flow_direction TEXT,

            payload JSONB NOT NULL,
            summary JSONB,

            status TEXT NOT NULL DEFAULT 'PENDING'
                CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED')),
            decision_reason TEXT,
            decided_by TEXT,
            decided_at TIMESTAMPTZ,

            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_vendor_change_requests_vendor_status
            ON control_plane.vendor_change_requests (requesting_vendor_code, status, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_vendor_change_requests_status_created
            ON control_plane.vendor_change_requests (status, created_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS control_plane.vendor_change_requests")
