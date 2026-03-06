"""Add control_plane.feature_gates table for configurable vendor approval flow.

Revision ID: v50
Revises: v49
Create Date: 2026-02-26

Admin can toggle per-feature whether vendor changes go through change_requests or apply immediately.
Schema matches existing application usage: gate_key, enabled, description.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v50"
down_revision: str | None = "v49"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_plane.feature_gates (
            gate_key TEXT PRIMARY KEY,
            enabled BOOLEAN NOT NULL,
            description TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    # Trigger to keep updated_at fresh on UPDATE
    op.execute(
        """
        CREATE OR REPLACE FUNCTION control_plane.trigger_set_feature_gates_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_feature_gates_updated_at ON control_plane.feature_gates"
    )
    op.execute(
        """
        CREATE TRIGGER trg_feature_gates_updated_at
            BEFORE UPDATE ON control_plane.feature_gates
            FOR EACH ROW
            EXECUTE FUNCTION control_plane.trigger_set_feature_gates_updated_at()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_feature_gates_updated_at ON control_plane.feature_gates")
    op.execute("DROP FUNCTION IF EXISTS control_plane.trigger_set_feature_gates_updated_at()")
    op.execute("DROP TABLE IF EXISTS control_plane.feature_gates")
