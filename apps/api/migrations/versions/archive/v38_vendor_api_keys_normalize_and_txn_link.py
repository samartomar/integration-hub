"""V38: Vendor API keys normalization + link transactions to api_key_id.

Phase 3 – Vendor API Keys & Cost Visibility.

- vendor_api_keys: add name, status (ACTIVE/INACTIVE/ROTATED), last_used_at; keep is_active for compat.
- data_plane.transactions: add api_key_id (nullable FK to vendor_api_keys.id).
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v38"
down_revision: str | None = "v37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE control_plane.vendor_api_keys
        ADD COLUMN IF NOT EXISTS name TEXT,
        ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'ACTIVE',
        ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMPTZ
    """)
    op.execute("""
        UPDATE control_plane.vendor_api_keys
        SET status = CASE WHEN COALESCE(is_active, true) THEN 'ACTIVE' ELSE 'INACTIVE' END
        WHERE status IS NULL
    """)
    op.execute("ALTER TABLE control_plane.vendor_api_keys DROP CONSTRAINT IF EXISTS chk_vendor_api_keys_status")
    op.execute("""
        ALTER TABLE control_plane.vendor_api_keys
        ADD CONSTRAINT chk_vendor_api_keys_status
        CHECK (status IN ('ACTIVE', 'INACTIVE', 'ROTATED'))
    """)
    op.execute("COMMENT ON COLUMN control_plane.vendor_api_keys.name IS 'e.g. Production App, Backoffice Integration'")
    op.execute("COMMENT ON COLUMN control_plane.vendor_api_keys.last_used_at IS 'Updated by routing lambda on auth'")
    op.execute("""
        ALTER TABLE data_plane.transactions
        ADD COLUMN IF NOT EXISTS api_key_id UUID
    """)
    op.execute("""
        COMMENT ON COLUMN data_plane.transactions.api_key_id IS
        'Resolved from auth. FK to control_plane.vendor_api_keys.id'
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE control_plane.vendor_api_keys DROP CONSTRAINT IF EXISTS chk_vendor_api_keys_status")
    op.execute("ALTER TABLE control_plane.vendor_api_keys DROP COLUMN IF EXISTS name")
    op.execute("ALTER TABLE control_plane.vendor_api_keys DROP COLUMN IF EXISTS status")
    op.execute("ALTER TABLE control_plane.vendor_api_keys DROP COLUMN IF EXISTS last_used_at")
    op.execute("ALTER TABLE data_plane.transactions DROP COLUMN IF EXISTS api_key_id")
