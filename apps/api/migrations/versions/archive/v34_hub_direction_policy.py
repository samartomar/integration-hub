"""V34: Add hub_direction_policy to operations.

Hub-level direction policy for canonical operations:
- service_outbound_only: hub exposes inbound service; vendors can only call it outbound
- exchange_bidirectional: peer/exchange; vendors can call and be called
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v34"
down_revision: str | None = "v33"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE control_plane.operations
        ADD COLUMN IF NOT EXISTS hub_direction_policy TEXT
    """)
    op.execute("""
        COMMENT ON COLUMN control_plane.operations.hub_direction_policy IS
        'service_outbound_only=hub service, vendors call only; exchange_bidirectional=peer exchange'
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE control_plane.operations
        DROP COLUMN IF EXISTS hub_direction_policy
    """)
