"""V41: Vendor API keys - created_by, created_via, key_suffix for self-service audit.

Adds:
- created_by TEXT NOT NULL DEFAULT 'admin' (values: 'admin' | 'vendor')
- created_via TEXT NULL (e.g. 'admin_ui' | 'vendor_portal' | 'api')
- key_suffix TEXT NULL (last 4 chars for masked display; set at creation only)
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v41"
down_revision: str | None = "v40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE control_plane.vendor_api_keys
        ADD COLUMN IF NOT EXISTS created_by TEXT NOT NULL DEFAULT 'admin',
        ADD COLUMN IF NOT EXISTS created_via TEXT,
        ADD COLUMN IF NOT EXISTS key_suffix TEXT
    """)
    op.execute("ALTER TABLE control_plane.vendor_api_keys DROP CONSTRAINT IF EXISTS chk_vendor_api_keys_created_by")
    op.execute("""
        ALTER TABLE control_plane.vendor_api_keys
        ADD CONSTRAINT chk_vendor_api_keys_created_by
        CHECK (created_by IN ('admin', 'vendor'))
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE control_plane.vendor_api_keys DROP CONSTRAINT IF EXISTS chk_vendor_api_keys_created_by")
    op.execute("ALTER TABLE control_plane.vendor_api_keys DROP COLUMN IF EXISTS created_by")
    op.execute("ALTER TABLE control_plane.vendor_api_keys DROP COLUMN IF EXISTS created_via")
    op.execute("ALTER TABLE control_plane.vendor_api_keys DROP COLUMN IF EXISTS key_suffix")
