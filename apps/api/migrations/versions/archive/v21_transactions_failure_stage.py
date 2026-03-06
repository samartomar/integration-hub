"""V21: Add failure_stage to data_plane.transactions (error metadata).

Revision ID: v21
Revises: v20
Create Date: 2025-02-19

Adds failure_stage text null. Together with v20 (error_code, http_status, retryable),
enables full error metadata persistence: error_code, http_status, retryable, failure_stage.
failure_stage values: details.stage (schema), DOWNSTREAM, MAPPING, CONFIG.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v21"
down_revision: str | None = "v20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE data_plane.transactions ADD COLUMN IF NOT EXISTS failure_stage TEXT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE data_plane.transactions DROP COLUMN IF EXISTS failure_stage")
