"""V40: Vendor export jobs table (Phase 5 scaffolding).

data_plane.vendor_export_jobs for per-vendor export requests.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v40"
down_revision: str | None = "v39"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS data_plane.vendor_export_jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_code TEXT NOT NULL,
            export_type TEXT NOT NULL,
            from_ts TIMESTAMPTZ NOT NULL,
            to_ts TIMESTAMPTZ NOT NULL,
            status TEXT NOT NULL DEFAULT 'QUEUED',
            s3_path TEXT,
            requested_by TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now(),
            completed_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_vendor_export_jobs_vendor_status
        ON data_plane.vendor_export_jobs (vendor_code, status)
    """)
    op.execute("COMMENT ON TABLE data_plane.vendor_export_jobs IS 'Per-vendor export requests. CONFIG_ONLY | TXN_7D | EVERYTHING'")
    op.execute("COMMENT ON COLUMN data_plane.vendor_export_jobs.export_type IS 'CONFIG_ONLY | TXN_7D | EVERYTHING'")
    op.execute("COMMENT ON COLUMN data_plane.vendor_export_jobs.status IS 'QUEUED | RUNNING | COMPLETED | FAILED'")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS data_plane.vendor_export_jobs")
