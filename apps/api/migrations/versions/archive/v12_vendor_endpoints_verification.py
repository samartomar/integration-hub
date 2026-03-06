"""V12: Add verification columns to control_plane.vendor_endpoints.

Revision ID: v12
Revises: v11
Create Date: 2025-02-13

- Adds verification_status TEXT NOT NULL DEFAULT 'PENDING'
- Adds last_verified_at TIMESTAMPTZ NULL
- Adds last_verification_error TEXT NULL
- Adds index on (vendor_code, operation_code, verification_status)
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v12"
down_revision: str | None = "v11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "idx_vendor_endpoints_vendor_op_verification"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE control_plane.vendor_endpoints "
        "ADD COLUMN IF NOT EXISTS verification_status TEXT NOT NULL DEFAULT 'PENDING'"
    )
    op.execute(
        "ALTER TABLE control_plane.vendor_endpoints "
        "ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMPTZ NULL"
    )
    op.execute(
        "ALTER TABLE control_plane.vendor_endpoints "
        "ADD COLUMN IF NOT EXISTS last_verification_error TEXT NULL"
    )
    op.execute(f"""
        CREATE INDEX IF NOT EXISTS {INDEX_NAME}
        ON control_plane.vendor_endpoints(vendor_code, operation_code, verification_status)
    """)


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS control_plane.{INDEX_NAME}")
    op.execute("""
        ALTER TABLE control_plane.vendor_endpoints
        DROP COLUMN IF EXISTS verification_status,
        DROP COLUMN IF EXISTS last_verified_at,
        DROP COLUMN IF EXISTS last_verification_error
    """)
