"""V15: Add control_plane.vendor_operation_mappings.

Revision ID: v15
Revises: v14
Create Date: 2025-02-18

- vendor_operation_mappings: field mapping rules per vendor+operation+version+direction
- direction: TO_CANONICAL | FROM_CANONICAL
- Indexes on (vendor_code, operation_code) and (vendor_code, operation_code, canonical_version)
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v15"
down_revision: str | None = "v14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS control_plane.vendor_operation_mappings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_code TEXT NOT NULL REFERENCES control_plane.vendors(vendor_code),
            operation_code TEXT NOT NULL REFERENCES control_plane.operations(operation_code),
            canonical_version TEXT NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('TO_CANONICAL', 'FROM_CANONICAL')),
            mapping JSONB NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (vendor_code, operation_code, canonical_version, direction)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vendor_operation_mappings_vendor_op "
        "ON control_plane.vendor_operation_mappings(vendor_code, operation_code)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vendor_operation_mappings_vendor_op_version "
        "ON control_plane.vendor_operation_mappings(vendor_code, operation_code, canonical_version)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS control_plane.idx_vendor_operation_mappings_vendor_op_version")
    op.execute("DROP INDEX IF EXISTS control_plane.idx_vendor_operation_mappings_vendor_op")
    op.execute("DROP TABLE IF EXISTS control_plane.vendor_operation_mappings")
