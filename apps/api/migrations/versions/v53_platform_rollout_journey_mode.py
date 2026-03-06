"""Add platform rollout tables for Journey Mode.

Revision ID: v53
Revises: v52
Create Date: 2026-03-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "v53"
down_revision: str | None = "v52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_plane.platform_features (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            feature_code TEXT NOT NULL UNIQUE,
            is_enabled BOOLEAN NULL DEFAULT NULL,
            description TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_plane.platform_phases (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            phase_code TEXT NOT NULL UNIQUE,
            phase_name TEXT NOT NULL,
            description TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_plane.platform_phase_features (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            phase_code TEXT NOT NULL
                REFERENCES control_plane.platform_phases(phase_code)
                ON DELETE CASCADE,
            feature_code TEXT NOT NULL
                REFERENCES control_plane.platform_features(feature_code)
                ON DELETE CASCADE,
            is_enabled BOOLEAN NOT NULL DEFAULT true,
            UNIQUE (phase_code, feature_code)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_plane.platform_settings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            settings_key TEXT NOT NULL UNIQUE,
            settings_value TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_platform_phase_features_phase_code "
        "ON control_plane.platform_phase_features(phase_code)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_platform_phase_features_feature_code "
        "ON control_plane.platform_phase_features(feature_code)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_platform_settings_key "
        "ON control_plane.platform_settings(settings_key)"
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION control_plane.trigger_set_platform_updated_at()
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
        DROP TRIGGER IF EXISTS trg_platform_features_updated_at
        ON control_plane.platform_features
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_platform_features_updated_at
            BEFORE UPDATE ON control_plane.platform_features
            FOR EACH ROW
            EXECUTE FUNCTION control_plane.trigger_set_platform_updated_at()
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_platform_phases_updated_at
        ON control_plane.platform_phases
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_platform_phases_updated_at
            BEFORE UPDATE ON control_plane.platform_phases
            FOR EACH ROW
            EXECUTE FUNCTION control_plane.trigger_set_platform_updated_at()
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_platform_settings_updated_at
        ON control_plane.platform_settings
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_platform_settings_updated_at
            BEFORE UPDATE ON control_plane.platform_settings
            FOR EACH ROW
            EXECUTE FUNCTION control_plane.trigger_set_platform_updated_at()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_platform_settings_updated_at ON control_plane.platform_settings"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_platform_phases_updated_at ON control_plane.platform_phases"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_platform_features_updated_at ON control_plane.platform_features"
    )
    op.execute("DROP FUNCTION IF EXISTS control_plane.trigger_set_platform_updated_at()")
    op.execute("DROP TABLE IF EXISTS control_plane.platform_settings")
    op.execute("DROP TABLE IF EXISTS control_plane.platform_phase_features")
    op.execute("DROP TABLE IF EXISTS control_plane.platform_phases")
    op.execute("DROP TABLE IF EXISTS control_plane.platform_features")
