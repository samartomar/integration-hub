"""V45: Rename hub_direction_policy to direction_policy.

Removes the 'hub' naming from the operations direction policy column.
Column semantics unchanged: PROVIDER_RECEIVES_ONLY | TWO_WAY.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v45"
down_revision: str | None = "v44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE control_plane.operations
        RENAME COLUMN hub_direction_policy TO direction_policy
    """)
    op.execute("""
        COMMENT ON COLUMN control_plane.operations.direction_policy IS
        'PROVIDER_RECEIVES_ONLY=licensees call provider; TWO_WAY=both can call each other'
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE control_plane.operations
        RENAME COLUMN direction_policy TO hub_direction_policy
    """)
    op.execute("""
        COMMENT ON COLUMN control_plane.operations.hub_direction_policy IS
        'PROVIDER_RECEIVES_ONLY=licensees call provider; TWO_WAY=both can call each other'
    """)

