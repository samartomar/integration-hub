"""V26: Add control_plane.auth_profiles and auth_profile_id on vendor_endpoints.

Revision ID: v26
Revises: v25
Create Date: 2025-02-21

- New table: control_plane.auth_profiles (downstream auth profiles per vendor)
- UNIQUE (vendor_code, name)
- Extend vendor_endpoints: auth_profile_id uuid NULL REFERENCES auth_profiles(id) ON DELETE SET NULL
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v26"
down_revision: str | None = "v25"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) Create control_plane.auth_profiles
    op.execute("""
        CREATE TABLE control_plane.auth_profiles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_code TEXT NOT NULL,
            name TEXT NOT NULL,
            auth_type TEXT NOT NULL,
            config JSONB NOT NULL DEFAULT '{}'::jsonb,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (vendor_code, name)
        )
    """)

    # 2) Add auth_profile_id to vendor_endpoints
    op.execute(
        "ALTER TABLE control_plane.vendor_endpoints "
        "ADD COLUMN IF NOT EXISTS auth_profile_id UUID NULL "
        "REFERENCES control_plane.auth_profiles(id) ON DELETE SET NULL"
    )


def downgrade() -> None:
    # Drop FK column from vendor_endpoints first
    op.execute(
        "ALTER TABLE control_plane.vendor_endpoints "
        "DROP COLUMN IF EXISTS auth_profile_id"
    )
    # Drop auth_profiles
    op.execute("DROP TABLE IF EXISTS control_plane.auth_profiles")
