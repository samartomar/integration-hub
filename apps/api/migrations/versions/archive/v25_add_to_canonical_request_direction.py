"""V25: Add TO_CANONICAL_REQUEST to vendor_operation_mappings direction CHECK.

Revision ID: v25
Revises: v24
Create Date: 2025-02-20

Source request mapping: vendor-specific params -> canonical request.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v25"
down_revision: str | None = "v24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE control_plane.vendor_operation_mappings
        DROP CONSTRAINT IF EXISTS vendor_operation_mappings_direction_check
    """)
    op.execute("""
        ALTER TABLE control_plane.vendor_operation_mappings
        ADD CONSTRAINT vendor_operation_mappings_direction_check
        CHECK (direction IN ('TO_CANONICAL', 'FROM_CANONICAL', 'TO_CANONICAL_RESPONSE', 'FROM_CANONICAL_RESPONSE', 'TO_CANONICAL_REQUEST'))
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE control_plane.vendor_operation_mappings
        DROP CONSTRAINT IF EXISTS vendor_operation_mappings_direction_check
    """)
    op.execute("""
        ALTER TABLE control_plane.vendor_operation_mappings
        ADD CONSTRAINT vendor_operation_mappings_direction_check
        CHECK (direction IN ('TO_CANONICAL', 'FROM_CANONICAL', 'TO_CANONICAL_RESPONSE', 'FROM_CANONICAL_RESPONSE'))
    """)
