"""V31: Add visual_model column to vendor_flow_layouts for Visual Flow Builder.

Stores the visual model (nodes, edges) used by the Visual Flow Builder.
Mappings (request_mapping, response_mapping) remain in vendor_operation_mappings.
This column is for UI state only; runtime routing reads only vendor_operation_mappings.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v31"
down_revision: str | None = "v30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE control_plane.vendor_flow_layouts
        ADD COLUMN IF NOT EXISTS visual_model JSONB
    """)
    op.execute(
        "COMMENT ON COLUMN control_plane.vendor_flow_layouts.visual_model IS "
        "'Visual Flow Builder: nodes and edges. UI-only; routing uses vendor_operation_mappings.'"
    )


def downgrade() -> None:
    op.execute("""
        ALTER TABLE control_plane.vendor_flow_layouts
        DROP COLUMN IF EXISTS visual_model
    """)

