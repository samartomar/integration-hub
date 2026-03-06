"""V32: Add supportsOutbound and supportsInbound to vendor_supported_operations.

Vendor explicitly declares which directions they intend to support when adding
a canonical operation. Used by readiness model and Visual Flow Builder.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v32"
down_revision: str | None = "v31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE control_plane.vendor_supported_operations
        ADD COLUMN IF NOT EXISTS supports_outbound BOOLEAN,
        ADD COLUMN IF NOT EXISTS supports_inbound BOOLEAN
    """)
    # Default existing rows to both directions for backward compatibility
    op.execute("""
        UPDATE control_plane.vendor_supported_operations
        SET supports_outbound = COALESCE(supports_outbound, true),
            supports_inbound = COALESCE(supports_inbound, true)
        WHERE supports_outbound IS NULL OR supports_inbound IS NULL
    """)
    op.execute(
        "COMMENT ON COLUMN control_plane.vendor_supported_operations.supports_outbound IS "
        "'Vendor declared intent: will call other APIs (outbound). Default true for existing rows.'"
    )
    op.execute(
        "COMMENT ON COLUMN control_plane.vendor_supported_operations.supports_inbound IS "
        "'Vendor declared intent: will receive calls (inbound). Default true for existing rows.'"
    )


def downgrade() -> None:
    op.execute("""
        ALTER TABLE control_plane.vendor_supported_operations
        DROP COLUMN IF EXISTS supports_outbound,
        DROP COLUMN IF EXISTS supports_inbound
    """)
