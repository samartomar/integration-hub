"""V42: Add UNIQUE constraint on (vendor_code, profile_name) in vendor_auth_profiles.

Ensures each vendor cannot have duplicate profile names.
Table is empty so no deduplication needed.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v42"
down_revision: str | None = "v41"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_vendor_auth_profiles_vendor_profile_name",
        "vendor_auth_profiles",
        ["vendor_code", "profile_name"],
        schema="control_plane",
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_vendor_auth_profiles_vendor_profile_name",
        "vendor_auth_profiles",
        schema="control_plane",
        type_="unique",
    )
