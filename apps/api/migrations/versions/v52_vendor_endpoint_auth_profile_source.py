"""Use vendor_auth_profiles for endpoint outbound auth.

Revision ID: v52
Revises: v51
Create Date: 2026-03-01

Adds vendor_endpoints.vendor_auth_profile_id (nullable) referencing
control_plane.vendor_auth_profiles(id) with ON DELETE SET NULL.
Legacy vendor_endpoints.auth_profile_id is intentionally preserved for now.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "v52"
down_revision: str | None = "v51"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) Endpoint reference to vendor-scoped auth profiles (new source of truth).
    op.execute(
        """
        ALTER TABLE control_plane.vendor_endpoints
        ADD COLUMN IF NOT EXISTS vendor_auth_profile_id UUID NULL
        """
    )
    op.execute(
        """
        ALTER TABLE control_plane.vendor_endpoints
        DROP CONSTRAINT IF EXISTS fk_vendor_endpoints_vendor_auth_profile_id
        """
    )
    op.execute(
        """
        ALTER TABLE control_plane.vendor_endpoints
        ADD CONSTRAINT fk_vendor_endpoints_vendor_auth_profile_id
        FOREIGN KEY (vendor_auth_profile_id)
        REFERENCES control_plane.vendor_auth_profiles(id)
        ON DELETE SET NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_vendor_endpoints_vendor_auth_profile_id
        ON control_plane.vendor_endpoints(vendor_auth_profile_id)
        """
    )

    # 2) Ensure ON CONFLICT (vendor_code, profile_name) works for vendor_auth_profiles upserts.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_vendor_auth_profiles_vendor_profile_name
        ON control_plane.vendor_auth_profiles(vendor_code, profile_name)
        """
    )

    # 3) Backfill migration intentionally no-op for demo/fresh environments.
    # Existing rows can be manually migrated later if needed.


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE control_plane.vendor_endpoints
        DROP CONSTRAINT IF EXISTS fk_vendor_endpoints_vendor_auth_profile_id
        """
    )
    op.execute(
        """
        DROP INDEX IF EXISTS control_plane.idx_vendor_endpoints_vendor_auth_profile_id
        """
    )
    op.execute(
        """
        ALTER TABLE control_plane.vendor_endpoints
        DROP COLUMN IF EXISTS vendor_auth_profile_id
        """
    )
    # Keep unique index for vendor_auth_profiles in downgrade to avoid destructive behavior on shared environments.
