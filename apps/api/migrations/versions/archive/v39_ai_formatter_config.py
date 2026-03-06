"""V39: AI formatter configuration plumbing (Phase 4).

Add columns to control_plane.operations for future AI human-friendly summary:
- ai_presentation_mode: RAW_ONLY | AI_SUMMARY_OPTIONAL | AI_SUMMARY_DEFAULT
- ai_formatter_prompt: TEXT (optional)
- ai_formatter_model: TEXT (optional)

Add optional columns to data_plane.transactions for storing results:
- ai_summary: TEXT
- ai_summary_model: TEXT
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v39"
down_revision: str | None = "v38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE control_plane.operations
        ADD COLUMN IF NOT EXISTS ai_presentation_mode TEXT DEFAULT 'RAW_ONLY',
        ADD COLUMN IF NOT EXISTS ai_formatter_prompt TEXT,
        ADD COLUMN IF NOT EXISTS ai_formatter_model TEXT
    """)
    op.execute("""
        UPDATE control_plane.operations
        SET ai_presentation_mode = COALESCE(ai_presentation_mode, 'RAW_ONLY')
        WHERE ai_presentation_mode IS NULL
    """)
    op.execute("COMMENT ON COLUMN control_plane.operations.ai_presentation_mode IS 'RAW_ONLY, AI_SUMMARY_OPTIONAL, AI_SUMMARY_DEFAULT'")
    op.execute("COMMENT ON COLUMN control_plane.operations.ai_formatter_prompt IS 'Optional prompt for AI human-friendly summary'")
    op.execute("""
        ALTER TABLE data_plane.transactions
        ADD COLUMN IF NOT EXISTS ai_summary TEXT,
        ADD COLUMN IF NOT EXISTS ai_summary_model TEXT
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE control_plane.operations DROP COLUMN IF EXISTS ai_presentation_mode")
    op.execute("ALTER TABLE control_plane.operations DROP COLUMN IF EXISTS ai_formatter_prompt")
    op.execute("ALTER TABLE control_plane.operations DROP COLUMN IF EXISTS ai_formatter_model")
    op.execute("ALTER TABLE data_plane.transactions DROP COLUMN IF EXISTS ai_summary")
    op.execute("ALTER TABLE data_plane.transactions DROP COLUMN IF EXISTS ai_summary_model")
