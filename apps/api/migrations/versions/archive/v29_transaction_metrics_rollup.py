"""V29: Pre-computed transaction metrics rollup for dashboards.

Creates data_plane.transaction_metrics_daily for fast aggregation.
Daily buckets (comment below: switch to hourly by changing date_trunc to 'hour' in rollup fn).

Schema:
- bucket_start: day boundary UTC (date_trunc('day', created_at))
- vendor_code: source or target vendor (we store rows for both; vendor "sees" both)
- direction: 'outbound' (vendor=source) or 'inbound' (vendor=target)
- operation: operation code
- status: transaction status
- count: number of transactions

Aggregation: Run rollup_transaction_metrics(from_ts, to_ts) periodically (Lambda/cron).
Incremental: Track last_bucket_processed in a small state table; only roll forward.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v29"
down_revision: str | None = "v28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS data_plane.transaction_metrics_daily (
            bucket_start TIMESTAMPTZ NOT NULL,
            vendor_code TEXT NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('outbound', 'inbound')),
            operation TEXT NOT NULL,
            status TEXT NOT NULL,
            count BIGINT NOT NULL DEFAULT 0,
            PRIMARY KEY (bucket_start, vendor_code, direction, operation, status)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tx_metrics_daily_vendor_bucket "
        "ON data_plane.transaction_metrics_daily (vendor_code, bucket_start)"
    )
    op.execute("COMMENT ON TABLE data_plane.transaction_metrics_daily IS "
               "'Pre-aggregated transaction counts. Daily buckets. Populate via rollup_transaction_metrics().'")

    # Function: roll up transactions in [from_ts, to_ts) into daily buckets.
    # Call periodically (e.g. Lambda every 15 min). Manages last_processed externally.
    op.execute("""
        CREATE OR REPLACE FUNCTION data_plane.rollup_transaction_metrics(p_from TIMESTAMPTZ, p_to TIMESTAMPTZ)
        RETURNS void
        LANGUAGE plpgsql
        AS $$
        BEGIN
            -- Outbound: source_vendor, created_at
            INSERT INTO data_plane.transaction_metrics_daily (bucket_start, vendor_code, direction, operation, status, count)
            SELECT
                date_trunc('day', created_at AT TIME ZONE 'UTC') AT TIME ZONE 'UTC',
                source_vendor,
                'outbound',
                COALESCE(operation, ''),
                COALESCE(status, ''),
                COUNT(*)::bigint
            FROM data_plane.transactions
            WHERE created_at >= p_from AND created_at < p_to AND source_vendor IS NOT NULL
            GROUP BY 1, 2, 3, 4, 5
            ON CONFLICT (bucket_start, vendor_code, direction, operation, status) DO UPDATE SET
                count = data_plane.transaction_metrics_daily.count + EXCLUDED.count;

            -- Inbound: target_vendor
            INSERT INTO data_plane.transaction_metrics_daily (bucket_start, vendor_code, direction, operation, status, count)
            SELECT
                date_trunc('day', created_at AT TIME ZONE 'UTC') AT TIME ZONE 'UTC',
                target_vendor,
                'inbound',
                COALESCE(operation, ''),
                COALESCE(status, ''),
                COUNT(*)::bigint
            FROM data_plane.transactions
            WHERE created_at >= p_from AND created_at < p_to AND target_vendor IS NOT NULL
            GROUP BY 1, 2, 3, 4, 5
            ON CONFLICT (bucket_start, vendor_code, direction, operation, status) DO UPDATE SET
                count = data_plane.transaction_metrics_daily.count + EXCLUDED.count;
        END;
        $$;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS data_plane.rollup_transaction_metrics(TIMESTAMPTZ, TIMESTAMPTZ)")
    op.execute("DROP TABLE IF EXISTS data_plane.transaction_metrics_daily")
