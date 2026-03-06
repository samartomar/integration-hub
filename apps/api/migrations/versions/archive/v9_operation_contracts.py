"""V9: Add control_plane.operation_contracts table.

Revision ID: v9
Revises: v8
Create Date: 2025-02-13
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v9"
down_revision: str | None = "v8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS control_plane.operation_contracts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            operation_code TEXT NOT NULL,
            canonical_version TEXT NOT NULL,
            request_schema JSONB NOT NULL,
            response_schema JSONB,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE(operation_code, canonical_version)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_operation_contracts_op_version_active "
        "ON control_plane.operation_contracts(operation_code, canonical_version, is_active)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS control_plane.idx_operation_contracts_op_version_active")
    op.execute("DROP TABLE IF EXISTS control_plane.operation_contracts")
