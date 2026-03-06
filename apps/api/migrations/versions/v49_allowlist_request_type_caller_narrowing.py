"""Expand allowlist request_type for caller narrowing.

Revision ID: v49
Revises: v48
Create Date: 2026-02-25

"""
from collections.abc import Sequence

from alembic import op

revision: str = "v49"
down_revision: str | None = "v48"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop old constraint (PostgreSQL names inline CHECK as {table}_{column}_check)
    op.execute(
        """
        ALTER TABLE control_plane.allowlist_change_requests
        DROP CONSTRAINT IF EXISTS allowlist_change_requests_request_type_check
        """
    )

    # Re-add with ALLOWLIST_RULE, PROVIDER_NARROWING, and CALLER_NARROWING
    op.execute(
        """
        ALTER TABLE control_plane.allowlist_change_requests
        ADD CONSTRAINT allowlist_change_requests_request_type_check
        CHECK (request_type IN ('ALLOWLIST_RULE', 'PROVIDER_NARROWING', 'CALLER_NARROWING'))
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE control_plane.allowlist_change_requests
        DROP CONSTRAINT IF EXISTS allowlist_change_requests_request_type_check
        """
    )

    op.execute(
        """
        ALTER TABLE control_plane.allowlist_change_requests
        ADD CONSTRAINT allowlist_change_requests_request_type_check
        CHECK (request_type IN ('ALLOWLIST_RULE', 'PROVIDER_NARROWING'))
        """
    )
