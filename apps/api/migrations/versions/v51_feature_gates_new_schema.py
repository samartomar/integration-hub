"""Migrate feature_gates to new schema: id, feature_code, vendor_code, is_enabled.

Revision ID: v51
Revises: v50
Create Date: 2026-02-26

Replaces gate_key/enabled/description with feature_code/vendor_code/is_enabled.
vendor_code NULL = global feature flag; non-null = vendor-specific override.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v51"
down_revision: str | None = "v50"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop old table (from v50: gate_key, enabled, description)
    op.execute("DROP TRIGGER IF EXISTS trg_feature_gates_updated_at ON control_plane.feature_gates")
    op.execute("DROP FUNCTION IF EXISTS control_plane.trigger_set_feature_gates_updated_at()")
    op.execute("DROP TABLE IF EXISTS control_plane.feature_gates")

    # Create new table (vendor_code NULL = global; partial unique enforces one global per feature_code)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_plane.feature_gates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            feature_code TEXT NOT NULL,
            vendor_code TEXT,
            is_enabled BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_feature_gates_feature_vendor "
        "ON control_plane.feature_gates (feature_code, vendor_code)"
    )
    # One global gate per feature_code (vendor_code IS NULL)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_feature_gates_global "
        "ON control_plane.feature_gates (feature_code) WHERE vendor_code IS NULL"
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
    op.execute("DROP INDEX IF EXISTS control_plane.idx_feature_gates_global")
    op.execute("DROP INDEX IF EXISTS control_plane.idx_feature_gates_feature_vendor")
    op.execute("DROP TABLE IF EXISTS control_plane.feature_gates")
    # Recreate v50 schema for downgrade
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
        """
        CREATE TRIGGER trg_feature_gates_updated_at
            BEFORE UPDATE ON control_plane.feature_gates
            FOR EACH ROW
            EXECUTE FUNCTION control_plane.trigger_set_feature_gates_updated_at()
        """
    )
