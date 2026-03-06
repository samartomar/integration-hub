"""V30: Add control_plane.vendor_flow_layouts for Visual Flow Builder.

Stores layout/UI metadata (node positions, labels, etc.) per vendor+operation+version.
One row per (vendor_code, operation_code, canonical_version).
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v30"
down_revision: str | None = "v29"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS control_plane.vendor_flow_layouts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_code TEXT NOT NULL REFERENCES control_plane.vendors(vendor_code),
            operation_code TEXT NOT NULL REFERENCES control_plane.operations(operation_code),
            canonical_version TEXT NOT NULL,
            layout JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (vendor_code, operation_code, canonical_version)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vendor_flow_layouts_vendor_op "
        "ON control_plane.vendor_flow_layouts(vendor_code, operation_code)"
    )
    op.execute(
        "COMMENT ON TABLE control_plane.vendor_flow_layouts IS "
        "'Visual Flow Builder: node positions, edges, UI state. One row per vendor+operation+version.'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS control_plane.idx_vendor_flow_layouts_vendor_op")
    op.execute("DROP TABLE IF EXISTS control_plane.vendor_flow_layouts")
