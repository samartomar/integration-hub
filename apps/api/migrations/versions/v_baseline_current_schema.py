"""Baseline: Current schema (squash of v1-v45).

Revision ID: baseline
Revises:
Create Date: 2025-02-23

Single migration representing the full schema after v45.
Use for: fresh DBs run upgrade; existing DBs run `alembic stamp baseline`.
"""
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from alembic import op
from sqlalchemy import text

revision: str = "baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS control_plane")
    op.execute("CREATE SCHEMA IF NOT EXISTS data_plane")

    # ---- control_plane ----
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_plane.vendors (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_code TEXT UNIQUE NOT NULL,
            vendor_name TEXT NOT NULL,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vendors_vendor_code "
        "ON control_plane.vendors(vendor_code)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_plane.operations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            operation_code TEXT UNIQUE NOT NULL,
            description TEXT,
            canonical_version TEXT,
            is_async_capable BOOLEAN DEFAULT true,
            is_active BOOLEAN DEFAULT true,
            direction_policy TEXT NOT NULL DEFAULT 'TWO_WAY'
                CHECK (direction_policy IN ('PROVIDER_RECEIVES_ONLY', 'TWO_WAY')),
            ai_presentation_mode TEXT DEFAULT 'RAW_ONLY',
            ai_formatter_prompt TEXT,
            ai_formatter_model TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_operations_operation_code "
        "ON control_plane.operations(operation_code)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_plane.auth_profiles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_code TEXT NOT NULL REFERENCES control_plane.vendors(vendor_code),
            name TEXT NOT NULL,
            auth_type TEXT NOT NULL,
            config JSONB NOT NULL DEFAULT '{}'::jsonb,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (vendor_code, name)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_plane.vendor_auth_profiles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_code TEXT NOT NULL REFERENCES control_plane.vendors(vendor_code),
            profile_name TEXT NOT NULL,
            auth_type TEXT NOT NULL,
            config JSONB NOT NULL,
            is_default BOOLEAN NOT NULL DEFAULT false,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vendor_auth_profiles_vendor_type_active "
        "ON control_plane.vendor_auth_profiles (vendor_code, auth_type, is_active)"
    )

    # control_plane.vendor_api_keys table removed (JWT-only auth)

    op.execute(
        """
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
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_operation_contracts_active
        ON control_plane.operation_contracts(operation_code, canonical_version)
        WHERE is_active = true
        """
    )

    # Robust allowlist: FKs + wildcard flags, no magic "*"/"HUB"
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_plane.vendor_operation_allowlist (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

            source_vendor_code TEXT REFERENCES control_plane.vendors(vendor_code),
            target_vendor_code TEXT REFERENCES control_plane.vendors(vendor_code),

            is_any_source BOOLEAN NOT NULL DEFAULT FALSE,
            is_any_target BOOLEAN NOT NULL DEFAULT FALSE,

            operation_code TEXT NOT NULL REFERENCES control_plane.operations(operation_code),

            rule_scope TEXT NOT NULL DEFAULT 'admin'
                CHECK (rule_scope IN ('admin', 'vendor')),

            flow_direction TEXT NOT NULL DEFAULT 'BOTH'
                CHECK (flow_direction IN ('INBOUND', 'OUTBOUND', 'BOTH')),

            created_at TIMESTAMPTZ DEFAULT now(),

            CHECK (
                (is_any_source = TRUE AND source_vendor_code IS NULL)
                OR (is_any_source = FALSE AND source_vendor_code IS NOT NULL)
            ),
            CHECK (
                (is_any_target = TRUE AND target_vendor_code IS NULL)
                OR (is_any_target = FALSE AND target_vendor_code IS NOT NULL)
            )
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_vendor_operation_allowlist_rule
        ON control_plane.vendor_operation_allowlist (
            COALESCE(source_vendor_code, '*'),
            is_any_source,
            COALESCE(target_vendor_code, '*'),
            is_any_target,
            operation_code,
            rule_scope,
            flow_direction
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vendor_operation_allowlist_source_target_op "
        "ON control_plane.vendor_operation_allowlist(source_vendor_code, target_vendor_code, operation_code)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_plane.vendor_supported_operations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_code TEXT NOT NULL REFERENCES control_plane.vendors(vendor_code),
            operation_code TEXT NOT NULL REFERENCES control_plane.operations(operation_code),
            is_active BOOLEAN NOT NULL DEFAULT true,
            canonical_version TEXT NOT NULL DEFAULT 'v1',
            flow_direction TEXT NOT NULL DEFAULT 'OUTBOUND'
                CHECK (flow_direction IN ('INBOUND', 'OUTBOUND')),
            supports_outbound BOOLEAN,
            supports_inbound BOOLEAN,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_vendor_supported_operations_active
        ON control_plane.vendor_supported_operations(vendor_code, operation_code, canonical_version, flow_direction)
        WHERE is_active = true
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vendor_supported_ops_flow_direction "
        "ON control_plane.vendor_supported_operations(vendor_code, flow_direction)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_plane.vendor_operation_contracts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_code TEXT NOT NULL REFERENCES control_plane.vendors(vendor_code),
            operation_code TEXT NOT NULL REFERENCES control_plane.operations(operation_code),
            canonical_version TEXT NOT NULL,
            flow_direction TEXT NOT NULL DEFAULT 'OUTBOUND'
                CHECK (flow_direction IN ('INBOUND', 'OUTBOUND')),
            request_schema JSONB NOT NULL,
            response_schema JSONB,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_vendor_operation_contracts_active
        ON control_plane.vendor_operation_contracts(vendor_code, operation_code, canonical_version, flow_direction)
        WHERE is_active = true
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_plane.vendor_operation_mappings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_code TEXT NOT NULL REFERENCES control_plane.vendors(vendor_code),
            operation_code TEXT NOT NULL REFERENCES control_plane.operations(operation_code),
            canonical_version TEXT NOT NULL,
            direction TEXT NOT NULL CHECK (
                direction IN (
                    'TO_CANONICAL',
                    'FROM_CANONICAL',
                    'TO_CANONICAL_RESPONSE',
                    'FROM_CANONICAL_RESPONSE'
                )
            ),
            flow_direction TEXT NOT NULL DEFAULT 'OUTBOUND'
                CHECK (flow_direction IN ('INBOUND', 'OUTBOUND')),
            mapping JSONB NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_vendor_operation_mappings_active
        ON control_plane.vendor_operation_mappings(
            vendor_code,
            operation_code,
            canonical_version,
            direction,
            flow_direction
        )
        WHERE is_active = true
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vendor_operation_mappings_vendor_op "
        "ON control_plane.vendor_operation_mappings(vendor_code, operation_code)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vendor_operation_mappings_vendor_op_version "
        "ON control_plane.vendor_operation_mappings(vendor_code, operation_code, canonical_version)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_plane.vendor_endpoints (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_code TEXT NOT NULL REFERENCES control_plane.vendors(vendor_code),
            operation_code TEXT NOT NULL REFERENCES control_plane.operations(operation_code),
            url TEXT NOT NULL,
            http_method TEXT,
            payload_format TEXT,
            timeout_ms INTEGER,
            is_active BOOLEAN DEFAULT true,
            flow_direction TEXT NOT NULL DEFAULT 'OUTBOUND'
                CHECK (flow_direction IN ('INBOUND', 'OUTBOUND')),
            auth_profile_id UUID REFERENCES control_plane.auth_profiles(id) ON DELETE SET NULL,
            verification_status TEXT NOT NULL DEFAULT 'PENDING',
            last_verified_at TIMESTAMPTZ,
            last_verification_error TEXT,
            verification_request JSONB,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_vendor_endpoints_active
        ON control_plane.vendor_endpoints(vendor_code, operation_code, flow_direction)
        WHERE is_active = true
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vendor_endpoints_vendor_operation "
        "ON control_plane.vendor_endpoints(vendor_code, operation_code)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vendor_endpoints_vendor_op_verification "
        "ON control_plane.vendor_endpoints(vendor_code, operation_code, verification_status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vendor_endpoints_flow_direction "
        "ON control_plane.vendor_endpoints(vendor_code, operation_code, flow_direction)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_plane.vendor_flow_layouts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_code TEXT NOT NULL REFERENCES control_plane.vendors(vendor_code),
            operation_code TEXT NOT NULL REFERENCES control_plane.operations(operation_code),
            canonical_version TEXT NOT NULL,
            layout JSONB NOT NULL DEFAULT '{}',
            visual_model JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (vendor_code, operation_code, canonical_version)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vendor_flow_layouts_vendor_op "
        "ON control_plane.vendor_flow_layouts(vendor_code, operation_code)"
    )

    # ---- data_plane ----
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS data_plane.idempotency_claims (
            source_vendor TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            transaction_id TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now(),
            PRIMARY KEY (source_vendor, idempotency_key)
        )
        """
    )

    conn = op.get_bind()

    # Partitioned transactions
    r = conn.execute(
        text(
            "SELECT c.relkind FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'data_plane' AND c.relname = 'transactions'"
        )
    )
    row = r.fetchone()
    if not row or row[0] != "p":
        conn.execute(
            text(
                """
                CREATE TABLE data_plane.transactions (
                    id UUID DEFAULT gen_random_uuid(),
                    transaction_id TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    source_vendor TEXT,
                    target_vendor TEXT,
                    operation TEXT,
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
                    api_key_id UUID,
                    ai_summary TEXT,
                    ai_summary_model TEXT,
                    PRIMARY KEY (id, created_at)
                ) PARTITION BY RANGE (created_at)
                """
            )
        )
        now = datetime.now(UTC)
        for i in range(-1, 3):
            d = now + timedelta(days=30 * i)
            yr, mo = d.year, d.month
            next_mo = mo + 1 if mo < 12 else 1
            next_yr = yr if mo < 12 else yr + 1
            from_ts = f"{yr}-{mo:02d}-01 00:00:00+00"
            to_ts = f"{next_yr}-{next_mo:02d}-01 00:00:00+00"
            part_name = f"transactions_{yr}_{mo:02d}"
            conn.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS data_plane.{part_name}
                    PARTITION OF data_plane.transactions
                    FOR VALUES FROM ('{from_ts}') TO ('{to_ts}')
                    """
                )
            )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS data_plane.transactions_default
                PARTITION OF data_plane.transactions DEFAULT
                """
            )
        )
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
            "CREATE INDEX IF NOT EXISTS idx_transactions_parent_transaction_id ON data_plane.transactions (parent_transaction_id)",
        ]:
            conn.execute(text(idx_sql))

    # Partitioned audit_events
    r = conn.execute(
        text(
            "SELECT c.relkind FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'data_plane' AND c.relname = 'audit_events'"
        )
    )
    row = r.fetchone()
    if not row or row[0] != "p":
        conn.execute(
            text(
                """
                CREATE TABLE data_plane.audit_events (
                    id UUID DEFAULT gen_random_uuid(),
                    transaction_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    vendor_code TEXT,
                    details JSONB,
                    created_at TIMESTAMPTZ DEFAULT now(),
                    PRIMARY KEY (id, created_at)
                ) PARTITION BY RANGE (created_at)
                """
            )
        )
        now = datetime.now(UTC)
        for i in range(-1, 3):
            d = now + timedelta(days=30 * i)
            yr, mo = d.year, d.month
            next_mo = mo + 1 if mo < 12 else 1
            next_yr = yr if mo < 12 else yr + 1
            from_ts = f"{yr}-{mo:02d}-01 00:00:00+00"
            to_ts = f"{next_yr}-{next_mo:02d}-01 00:00:00+00"
            part_name = f"audit_events_{yr}_{mo:02d}"
            conn.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS data_plane.{part_name}
                    PARTITION OF data_plane.audit_events
                    FOR VALUES FROM ('{from_ts}') TO ('{to_ts}')
                    """
                )
            )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS data_plane.audit_events_default
                PARTITION OF data_plane.audit_events DEFAULT
                """
            )
        )
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS idx_audit_events_transaction_id_created ON data_plane.audit_events (transaction_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_audit_events_created_at ON data_plane.audit_events (created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_audit_events_vendor_code ON data_plane.audit_events (vendor_code)",
        ]:
            conn.execute(text(idx_sql))

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS data_plane.transaction_metrics_daily (
            bucket_start TIMESTAMPTZ NOT NULL,
            vendor_code TEXT NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('outbound', 'inbound')),
            operation TEXT NOT NULL,
            status TEXT NOT NULL,
            count BIGINT NOT NULL DEFAULT 0,
            PRIMARY KEY (bucket_start, vendor_code, direction, operation, status)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tx_metrics_daily_vendor_bucket "
        "ON data_plane.transaction_metrics_daily (vendor_code, bucket_start)"
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION data_plane.rollup_transaction_metrics(
            p_from TIMESTAMPTZ,
            p_to   TIMESTAMPTZ
        )
        RETURNS void
        LANGUAGE plpgsql
        AS $$
        BEGIN
            INSERT INTO data_plane.transaction_metrics_daily (
                bucket_start, vendor_code, direction, operation, status, count
            )
            SELECT
                date_trunc('day', created_at AT TIME ZONE 'UTC') AT TIME ZONE 'UTC',
                source_vendor,
                'outbound',
                COALESCE(operation, ''),
                COALESCE(status, ''),
                COUNT(*)::bigint
            FROM data_plane.transactions
            WHERE created_at >= p_from
              AND created_at <  p_to
              AND source_vendor IS NOT NULL
            GROUP BY 1, 2, 3, 4, 5
            ON CONFLICT (bucket_start, vendor_code, direction, operation, status)
            DO UPDATE SET count = data_plane.transaction_metrics_daily.count + EXCLUDED.count;

            INSERT INTO data_plane.transaction_metrics_daily (
                bucket_start, vendor_code, direction, operation, status, count
            )
            SELECT
                date_trunc('day', created_at AT TIME ZONE 'UTC') AT TIME ZONE 'UTC',
                target_vendor,
                'inbound',
                COALESCE(operation, ''),
                COALESCE(status, ''),
                COUNT(*)::bigint
            FROM data_plane.transactions
            WHERE created_at >= p_from
              AND created_at <  p_to
              AND target_vendor IS NOT NULL
            GROUP BY 1, 2, 3, 4, 5
            ON CONFLICT (bucket_start, vendor_code, direction, operation, status)
            DO UPDATE SET count = data_plane.transaction_metrics_daily.count + EXCLUDED.count;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS data_plane.vendor_export_jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_code TEXT NOT NULL REFERENCES control_plane.vendors(vendor_code),
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
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vendor_export_jobs_vendor_status "
        "ON data_plane.vendor_export_jobs (vendor_code, status)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS data_plane.vendor_export_jobs")
    op.execute("DROP FUNCTION IF EXISTS data_plane.rollup_transaction_metrics(TIMESTAMPTZ, TIMESTAMPTZ)")
    op.execute("DROP TABLE IF EXISTS data_plane.transaction_metrics_daily")
    op.execute("DROP TABLE IF EXISTS data_plane.audit_events CASCADE")
    op.execute("DROP TABLE IF EXISTS data_plane.transactions CASCADE")
    op.execute("DROP TABLE IF EXISTS data_plane.idempotency_claims")

    op.execute("DROP TABLE IF EXISTS control_plane.vendor_flow_layouts")
    op.execute("DROP TABLE IF EXISTS control_plane.vendor_endpoints")
    op.execute("DROP TABLE IF EXISTS control_plane.vendor_operation_mappings")
    op.execute("DROP TABLE IF EXISTS control_plane.vendor_operation_contracts")
    op.execute("DROP TABLE IF EXISTS control_plane.vendor_supported_operations")
    op.execute("DROP INDEX IF EXISTS uq_vendor_operation_allowlist_rule")
    op.execute("DROP TABLE IF EXISTS control_plane.vendor_operation_allowlist")
    op.execute("DROP TABLE IF EXISTS control_plane.operation_contracts")
    op.execute("DROP TABLE IF EXISTS control_plane.vendor_api_keys")
    op.execute("DROP TABLE IF EXISTS control_plane.vendor_auth_profiles")
    op.execute("DROP TABLE IF EXISTS control_plane.auth_profiles")
    op.execute("DROP TABLE IF EXISTS control_plane.operations")
    op.execute("DROP TABLE IF EXISTS control_plane.vendors")
    op.execute("DROP SCHEMA IF EXISTS data_plane")
    op.execute("DROP SCHEMA IF EXISTS control_plane")