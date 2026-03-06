"""V11: Add control_plane.vendor_api_keys for API key -> vendor mapping.

Revision ID: v11
Revises: v10
Create Date: 2025-02-13

  is_active, created_at, updated_at.
- Index on vendor_code.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v11"
down_revision: str | None = "v10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS control_plane.vendor_api_keys (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_code TEXT NOT NULL,
            api_key_id TEXT NOT NULL,
            api_key_hash TEXT NOT NULL,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now(),
            CONSTRAINT uq_vendor_api_keys_id UNIQUE (api_key_id),
            CONSTRAINT uq_vendor_api_keys_hash UNIQUE (api_key_hash)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vendor_api_keys_vendor_code "
        "ON control_plane.vendor_api_keys(vendor_code)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS control_plane.vendor_api_keys")
