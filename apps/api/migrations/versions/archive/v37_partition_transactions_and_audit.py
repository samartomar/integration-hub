"""V37: Partition data_plane.transactions and audit_events by created_at.

Phase 1 - Partitioned Data Plane for 100B+ transactions/year scale.

- transactions: RANGE partition by created_at. Default + monthly partitions.
  Idempotency: data_plane.idempotency_claims (non-partitioned) - PG unique on
  partitioned tables must include partition key.
- audit_events: Same RANGE partitioning.

Migration path:
1. Create idempotency_claims, backfill from transactions.
2. Rename transactions->transactions_old, create partitioned transactions, copy, drop old.
3. Same for audit_events.
4. Create indexes.

Idempotent: skips if already partitioned. Downtime: copy+swap (seconds for POC).
"""
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from alembic import op
from sqlalchemy import text

revision: str = "v37"
down_revision: str | None = "v36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _run(conn, sql_str: str):
    conn.execute(text(sql_str))


def _partition_transactions(conn) -> None:
    """Convert transactions to partitioned table."""
    r = conn.execute(text(
        "SELECT c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'data_plane' AND c.relname = 'transactions'"
    ))
    row = r.fetchone()
    if row and row[0] == "p":  # p = partitioned
        return

    _run(conn, """
        CREATE TABLE IF NOT EXISTS data_plane.idempotency_claims (
            source_vendor TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            transaction_id TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now(),
            PRIMARY KEY (source_vendor, idempotency_key)
        )
    """)
    _run(conn, "COMMENT ON TABLE data_plane.idempotency_claims IS "
         "'Non-partitioned idempotency lookup for routing lambda.'")

    _run(conn, """
        INSERT INTO data_plane.idempotency_claims (source_vendor, idempotency_key, transaction_id, created_at)
        SELECT DISTINCT ON (source_vendor, idempotency_key)
               source_vendor, idempotency_key, transaction_id, created_at
        FROM data_plane.transactions
        WHERE source_vendor IS NOT NULL AND idempotency_key IS NOT NULL AND TRIM(idempotency_key) != ''
        ORDER BY source_vendor, idempotency_key, created_at ASC
        ON CONFLICT (source_vendor, idempotency_key) DO NOTHING
    """)

    _run(conn, "ALTER TABLE data_plane.transactions RENAME TO transactions_old")

    _run(conn, """
        CREATE TABLE data_plane.transactions (
            id UUID DEFAULT gen_random_uuid(),
            transaction_id TEXT NOT NULL,
            correlation_id TEXT NOT NULL,
            source_vendor TEXT NOT NULL,
            target_vendor TEXT NOT NULL,
            operation TEXT NOT NULL,
            idempotency_key TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ DEFAULT now(),
            request_body JSONB,
            response_body JSONB,
            canonical_request JSONB,
            target_request JSONB,
            canonical_request_body JSONB,
            target_request_body JSONB,
            target_response_body JSONB,
            canonical_response_body JSONB,
            parent_transaction_id UUID,
            redrive_count INT NOT NULL DEFAULT 0,
            error_code TEXT,
            http_status INTEGER,
            retryable BOOLEAN,
            failure_stage TEXT,
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
    """)

    now = datetime.now(UTC)
    for i in range(-1, 3):
        d = now + timedelta(days=30 * i)
        yr, mo = d.year, d.month
        next_mo = mo + 1 if mo < 12 else 1
        next_yr = yr if mo < 12 else yr + 1
        from_ts = f"{yr}-{mo:02d}-01 00:00:00+00"
        to_ts = f"{next_yr}-{next_mo:02d}-01 00:00:00+00"
        part_name = f"transactions_{yr}_{mo:02d}"
        _run(conn, f"""
            CREATE TABLE IF NOT EXISTS data_plane.{part_name}
            PARTITION OF data_plane.transactions
            FOR VALUES FROM ('{from_ts}') TO ('{to_ts}')
        """)
    _run(conn, """
        CREATE TABLE IF NOT EXISTS data_plane.transactions_default
        PARTITION OF data_plane.transactions DEFAULT
    """)

    _run(conn, """
        INSERT INTO data_plane.transactions
        SELECT id, transaction_id, correlation_id, source_vendor, target_vendor, operation,
               idempotency_key, status, created_at,
               request_body, response_body, canonical_request, target_request,
               canonical_request_body, target_request_body,
               target_response_body, canonical_response_body,
               parent_transaction_id, redrive_count,
               error_code, http_status, retryable, failure_stage
        FROM data_plane.transactions_old
    """)
    _run(conn, "DROP TABLE data_plane.transactions_old")

    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_transactions_transaction_id ON data_plane.transactions (transaction_id)",
        "CREATE INDEX IF NOT EXISTS idx_transactions_correlation_id ON data_plane.transactions (correlation_id)",
        "CREATE INDEX IF NOT EXISTS idx_transactions_idempotency_key ON data_plane.transactions (idempotency_key)",
        "CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON data_plane.transactions (created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_transactions_audit_vendor_created ON data_plane.transactions (source_vendor, created_at DESC, transaction_id)",
        "CREATE INDEX IF NOT EXISTS idx_transactions_source_vendor_created_at ON data_plane.transactions (source_vendor, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_transactions_target_vendor_created_at ON data_plane.transactions (target_vendor, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_transactions_source_op_created ON data_plane.transactions (source_vendor, operation, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_transactions_target_op_created ON data_plane.transactions (target_vendor, operation, created_at DESC)",
    ]:
        _run(conn, idx_sql)


def _partition_audit_events(conn) -> None:
    """Convert audit_events to partitioned table."""
    r = conn.execute(text(
        "SELECT c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'data_plane' AND c.relname = 'audit_events'"
    ))
    row = r.fetchone()
    if row and row[0] == "p":
        return
    _run(conn, "ALTER TABLE data_plane.audit_events RENAME TO audit_events_old")
    _run(conn, """
        CREATE TABLE data_plane.audit_events (
            id UUID DEFAULT gen_random_uuid(),
            transaction_id TEXT NOT NULL,
            action TEXT NOT NULL,
            vendor_code TEXT,
            details JSONB,
            created_at TIMESTAMPTZ DEFAULT now(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
    """)
    now = datetime.now(UTC)
    for i in range(-1, 3):
        d = now + timedelta(days=30 * i)
        yr, mo = d.year, d.month
        next_mo = mo + 1 if mo < 12 else 1
        next_yr = yr if mo < 12 else yr + 1
        from_ts = f"{yr}-{mo:02d}-01 00:00:00+00"
        to_ts = f"{next_yr}-{next_mo:02d}-01 00:00:00+00"
        part_name = f"audit_events_{yr}_{mo:02d}"
        _run(conn, f"""
            CREATE TABLE IF NOT EXISTS data_plane.{part_name}
            PARTITION OF data_plane.audit_events
            FOR VALUES FROM ('{from_ts}') TO ('{to_ts}')
        """)
    _run(conn, """
        CREATE TABLE IF NOT EXISTS data_plane.audit_events_default
        PARTITION OF data_plane.audit_events DEFAULT
    """)
    _run(conn, """
        INSERT INTO data_plane.audit_events
        SELECT id, transaction_id, action, vendor_code, details, created_at
        FROM data_plane.audit_events_old
    """)
    _run(conn, "DROP TABLE data_plane.audit_events_old")
    _run(conn, "CREATE INDEX IF NOT EXISTS idx_audit_events_transaction_id_created ON data_plane.audit_events (transaction_id, created_at)")
    _run(conn, "CREATE INDEX IF NOT EXISTS idx_audit_events_created_at ON data_plane.audit_events (created_at DESC)")
    _run(conn, "CREATE INDEX IF NOT EXISTS idx_audit_events_vendor_code ON data_plane.audit_events (vendor_code)")


def upgrade() -> None:
    conn = op.get_bind()
    # Use raw connection for execute
    try:
        _partition_transactions(conn)
    except Exception:
        # If transactions_old exists, we might have partially failed; try to recover
        conn.execute("SELECT 1")
        raise
    _partition_audit_events(conn)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS data_plane.idempotency_claims")
    # Downgrade would require recreating non-partitioned tables - complex; leave as no-op for safety
    # Document in PARTITIONING_DESIGN.md that downgrade is not implemented
    pass
