"""Add policy decision observability table.

Revision ID: v54
Revises: v53
Create Date: 2026-03-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "v54"
down_revision: str | None = "v53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS policy")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS policy.policy_decisions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            surface TEXT,
            action TEXT,
            vendor_code TEXT,
            target_vendor_code TEXT,
            operation_code TEXT,
            decision_code TEXT,
            allowed BOOLEAN,
            http_status INTEGER,
            correlation_id TEXT,
            transaction_id TEXT,
            metadata JSONB
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_policy_decisions_vendor_occurred
        ON policy.policy_decisions (vendor_code, occurred_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_policy_decisions_operation_occurred
        ON policy.policy_decisions (operation_code, occurred_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_policy_decisions_decision_occurred
        ON policy.policy_decisions (decision_code, occurred_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS policy.policy_decisions")
