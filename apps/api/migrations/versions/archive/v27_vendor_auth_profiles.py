"""V27: Add control_plane.vendor_auth_profiles for inbound auth (JWT, etc.).

Revision ID: v27
Revises: v26
Create Date: 2025-02-22

Inbound auth profiles: how vendors authenticate to the Hub (API_KEY, JWT_IDP, etc.).
Separate from auth_profiles (downstream/outbound auth to target vendors).
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v27"
down_revision: str | None = "v26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE control_plane.vendor_auth_profiles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_code TEXT NOT NULL,
            profile_name TEXT NOT NULL,
            auth_type TEXT NOT NULL,
            config JSONB NOT NULL,
            is_default BOOLEAN NOT NULL DEFAULT false,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX ix_vendor_auth_profiles_vendor_type_active "
        "ON control_plane.vendor_auth_profiles (vendor_code, auth_type, is_active)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_vendor_auth_profiles_vendor_type_active")
    op.execute("DROP TABLE IF EXISTS control_plane.vendor_auth_profiles")
