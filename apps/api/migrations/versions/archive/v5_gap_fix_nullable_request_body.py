"""V5: GAP FIX - Allow NULL for source_vendor/target_vendor/operation on validation_failed; add request_body.

Revision ID: v5
Revises: v4
Create Date: 2025-02-13
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v5"
down_revision: str | None = "v4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE data_plane.transactions ALTER COLUMN source_vendor DROP NOT NULL"
    )
    op.execute(
        "ALTER TABLE data_plane.transactions ALTER COLUMN target_vendor DROP NOT NULL"
    )
    op.execute(
        "ALTER TABLE data_plane.transactions ALTER COLUMN operation DROP NOT NULL"
    )
    op.execute(
        "ALTER TABLE data_plane.transactions ADD COLUMN IF NOT EXISTS request_body JSONB"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE data_plane.transactions ALTER COLUMN source_vendor SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE data_plane.transactions ALTER COLUMN target_vendor SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE data_plane.transactions ALTER COLUMN operation SET NOT NULL"
    )
    op.execute("ALTER TABLE data_plane.transactions DROP COLUMN IF EXISTS request_body")
