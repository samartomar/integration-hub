"""V44: Unify operation direction policy to PROVIDER_RECEIVES_ONLY and TWO_WAY.

Maps legacy hub_direction_policy values to new enum:
- service_outbound_only -> PROVIDER_RECEIVES_ONLY
- exchange_bidirectional -> TWO_WAY
- NULL -> TWO_WAY (default)
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v44"
down_revision: str | None = "v43"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        UPDATE control_plane.operations
        SET hub_direction_policy = 'PROVIDER_RECEIVES_ONLY'
        WHERE LOWER(TRIM(COALESCE(hub_direction_policy, ''))) = 'service_outbound_only'
    """)
    op.execute("""
        UPDATE control_plane.operations
        SET hub_direction_policy = 'TWO_WAY'
        WHERE LOWER(TRIM(COALESCE(hub_direction_policy, ''))) = 'exchange_bidirectional'
           OR hub_direction_policy IS NULL
           OR TRIM(hub_direction_policy) = ''
    """)
    op.execute("""
        COMMENT ON COLUMN control_plane.operations.hub_direction_policy IS
        'PROVIDER_RECEIVES_ONLY=licensees call provider; TWO_WAY=both can call each other'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE control_plane.operations
        SET hub_direction_policy = 'service_outbound_only'
        WHERE UPPER(TRIM(hub_direction_policy)) = 'PROVIDER_RECEIVES_ONLY'
    """)
    op.execute("""
        UPDATE control_plane.operations
        SET hub_direction_policy = 'exchange_bidirectional'
        WHERE UPPER(TRIM(hub_direction_policy)) = 'TWO_WAY'
    """)
    op.execute("""
        COMMENT ON COLUMN control_plane.operations.hub_direction_policy IS
        'service_outbound_only=hub service, vendors call only; exchange_bidirectional=peer exchange'
    """)

