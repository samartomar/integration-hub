"""V20: Add debug payload tier columns to data_plane.transactions.

Revision ID: v20
Revises: v19
Create Date: 2025-02-19

Adds nullable columns for debug/audit tier:
- error_code text null
- http_status int null
- retryable bool null

(canonical_request_body, target_request_body, target_response_body, canonical_response_body
 already exist from v18/v19)
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v20"
down_revision: str | None = "v19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE data_plane.transactions ADD COLUMN IF NOT EXISTS error_code TEXT"
    )
    op.execute(
        "ALTER TABLE data_plane.transactions ADD COLUMN IF NOT EXISTS http_status INTEGER"
    )
    op.execute(
        "ALTER TABLE data_plane.transactions ADD COLUMN IF NOT EXISTS retryable BOOLEAN"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE data_plane.transactions DROP COLUMN IF EXISTS retryable")
    op.execute("ALTER TABLE data_plane.transactions DROP COLUMN IF EXISTS http_status")
    op.execute("ALTER TABLE data_plane.transactions DROP COLUMN IF EXISTS error_code")
