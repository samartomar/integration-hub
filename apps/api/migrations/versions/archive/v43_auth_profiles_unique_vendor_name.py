"""V43: Ensure auth_profiles has UNIQUE (vendor_code, name) for ON CONFLICT.

Fixes 'there is no unique or exclusion constraint matching the ON CONFLICT
specification' when POST /v1/vendor/auth-profiles or registry auth-profiles
uses INSERT ... ON CONFLICT (vendor_code, name).

v26 creates the table with UNIQUE inline; this migration adds the constraint
if missing (e.g. DB created via different path).
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v43"
down_revision: str | None = "v42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add unique constraint if missing (fixes ON CONFLICT error).
    # v26 creates it inline; this handles DBs where it was missing.
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE control_plane.auth_profiles
            ADD CONSTRAINT uq_auth_profiles_vendor_name UNIQUE (vendor_code, name);
        EXCEPTION
            WHEN duplicate_object THEN NULL;  -- constraint/index already exists
        END $$;
    """)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE control_plane.auth_profiles "
        "DROP CONSTRAINT IF EXISTS uq_auth_profiles_vendor_name"
    )
