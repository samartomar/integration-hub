"""V17: Extend vendor_operation_mappings direction for response transforms.

Revision ID: v17
Revises: v16
Create Date: 2025-02-18

- Add TO_CANONICAL_RESPONSE, FROM_CANONICAL_RESPONSE to direction CHECK
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v17"
down_revision: str | None = "v16"
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
        CHECK (direction IN ('TO_CANONICAL', 'FROM_CANONICAL', 'TO_CANONICAL_RESPONSE', 'FROM_CANONICAL_RESPONSE'))
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE control_plane.vendor_operation_mappings
        DROP CONSTRAINT IF EXISTS vendor_operation_mappings_direction_check
    """)
    op.execute("""
        ALTER TABLE control_plane.vendor_operation_mappings
        ADD CONSTRAINT vendor_operation_mappings_direction_check
        CHECK (direction IN ('TO_CANONICAL', 'FROM_CANONICAL'))
    """)
