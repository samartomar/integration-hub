"""V22: Add verification_request JSONB to control_plane.vendor_endpoints.

Revision ID: v22
Revises: v21
Create Date: 2025-02-19

Adds verification_request JSONB NULL for vendor-owned endpoint verification.
Vendors can persist a custom payload to send when verifying the endpoint.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v22"
down_revision: str | None = "v21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE control_plane.vendor_endpoints "
        "ADD COLUMN IF NOT EXISTS verification_request JSONB NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE control_plane.vendor_endpoints "
        "DROP COLUMN IF EXISTS verification_request"
    )
