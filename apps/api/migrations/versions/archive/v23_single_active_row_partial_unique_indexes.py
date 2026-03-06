"""V23: Enforce single active row with partial unique indexes.

Revision ID: v23
Revises: v22
Create Date: 2025-02-19

Adds partial unique indexes WHERE is_active = true for:
- control_plane.operation_contracts
- control_plane.vendor_operation_contracts
- control_plane.vendor_endpoints
- control_plane.vendor_operation_mappings

Before creating indexes, deactivates duplicate active rows (keeps newest by updated_at).
Idempotent: safe to run multiple times.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v23"
down_revision: str | None = "v22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Partial unique index names
IDX_OP_CONTRACTS = "uq_operation_contracts_single_active"
IDX_VENDOR_OP_CONTRACTS = "uq_vendor_operation_contracts_single_active"
IDX_VENDOR_ENDPOINTS = "uq_vendor_endpoints_single_active"
IDX_VENDOR_OP_MAPPINGS = "uq_vendor_operation_mappings_single_active"


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1) operation_contracts: (operation_code, canonical_version) WHERE is_active
    # -------------------------------------------------------------------------
    _drop_unique_constraint("control_plane", "operation_contracts")
    _deactivate_duplicates_operation_contracts()
    op.execute(f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {IDX_OP_CONTRACTS}
        ON control_plane.operation_contracts (operation_code, canonical_version)
        WHERE is_active = true
    """)

    # -------------------------------------------------------------------------
    # 2) vendor_operation_contracts
    # -------------------------------------------------------------------------
    _drop_unique_constraint("control_plane", "vendor_operation_contracts")
    _deactivate_duplicates_vendor_operation_contracts()
    op.execute(f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {IDX_VENDOR_OP_CONTRACTS}
        ON control_plane.vendor_operation_contracts (vendor_code, operation_code, canonical_version)
        WHERE is_active = true
    """)

    # -------------------------------------------------------------------------
    # 3) vendor_endpoints
    # -------------------------------------------------------------------------
    _drop_unique_constraint("control_plane", "vendor_endpoints")
    _deactivate_duplicates_vendor_endpoints()
    op.execute(f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {IDX_VENDOR_ENDPOINTS}
        ON control_plane.vendor_endpoints (vendor_code, operation_code)
        WHERE is_active = true
    """)

    # -------------------------------------------------------------------------
    # 4) vendor_operation_mappings
    # -------------------------------------------------------------------------
    _drop_unique_constraint("control_plane", "vendor_operation_mappings")
    _deactivate_duplicates_vendor_operation_mappings()
    op.execute(f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {IDX_VENDOR_OP_MAPPINGS}
        ON control_plane.vendor_operation_mappings (vendor_code, operation_code, canonical_version, direction)
        WHERE is_active = true
    """)


def _drop_unique_constraint(schema: str, table: str) -> None:
    """Drop unique constraint on table (finds by pg_constraint, handles truncation)."""
    op.execute(f"""
        DO $$
        DECLARE
            cname text;
        BEGIN
            SELECT conname INTO cname
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = '{schema}' AND t.relname = '{table}' AND c.contype = 'u'
            LIMIT 1;
            IF cname IS NOT NULL THEN
                EXECUTE format('ALTER TABLE {schema}.{table} DROP CONSTRAINT %I', cname);
                RAISE NOTICE 'v23: dropped unique constraint % on %.%', cname, '{schema}', '{table}';
            END IF;
        END $$;
    """)


def _deactivate_duplicates_operation_contracts() -> None:
    op.execute("""
        DO $$
        DECLARE
            r_count int;
        BEGIN
            WITH ranked AS (
                SELECT id, row_number() OVER (
                    PARTITION BY operation_code, canonical_version
                    ORDER BY updated_at DESC NULLS LAST
                ) AS rn
                FROM control_plane.operation_contracts
                WHERE is_active = true
            ),
            to_deactivate AS (SELECT id FROM ranked WHERE rn > 1)
            UPDATE control_plane.operation_contracts t
            SET is_active = false
            FROM to_deactivate td
            WHERE t.id = td.id;
            GET DIAGNOSTICS r_count = ROW_COUNT;
            IF r_count > 0 THEN
                RAISE NOTICE 'v23: deactivated % duplicate(s) in control_plane.operation_contracts', r_count;
            END IF;
        END $$;
    """)


def _deactivate_duplicates_vendor_operation_contracts() -> None:
    op.execute("""
        DO $$
        DECLARE
            r_count int;
        BEGIN
            WITH ranked AS (
                SELECT id, row_number() OVER (
                    PARTITION BY vendor_code, operation_code, canonical_version
                    ORDER BY updated_at DESC NULLS LAST
                ) AS rn
                FROM control_plane.vendor_operation_contracts
                WHERE is_active = true
            ),
            to_deactivate AS (SELECT id FROM ranked WHERE rn > 1)
            UPDATE control_plane.vendor_operation_contracts t
            SET is_active = false
            FROM to_deactivate td
            WHERE t.id = td.id;
            GET DIAGNOSTICS r_count = ROW_COUNT;
            IF r_count > 0 THEN
                RAISE NOTICE 'v23: deactivated % duplicate(s) in control_plane.vendor_operation_contracts', r_count;
            END IF;
        END $$;
    """)


def _deactivate_duplicates_vendor_endpoints() -> None:
    op.execute("""
        DO $$
        DECLARE
            r_count int;
        BEGIN
            WITH ranked AS (
                SELECT id, row_number() OVER (
                    PARTITION BY vendor_code, operation_code
                    ORDER BY updated_at DESC NULLS LAST
                ) AS rn
                FROM control_plane.vendor_endpoints
                WHERE is_active = true
            ),
            to_deactivate AS (SELECT id FROM ranked WHERE rn > 1)
            UPDATE control_plane.vendor_endpoints t
            SET is_active = false
            FROM to_deactivate td
            WHERE t.id = td.id;
            GET DIAGNOSTICS r_count = ROW_COUNT;
            IF r_count > 0 THEN
                RAISE NOTICE 'v23: deactivated % duplicate(s) in control_plane.vendor_endpoints', r_count;
            END IF;
        END $$;
    """)


def _deactivate_duplicates_vendor_operation_mappings() -> None:
    op.execute("""
        DO $$
        DECLARE
            r_count int;
        BEGIN
            WITH ranked AS (
                SELECT id, row_number() OVER (
                    PARTITION BY vendor_code, operation_code, canonical_version, direction
                    ORDER BY updated_at DESC NULLS LAST
                ) AS rn
                FROM control_plane.vendor_operation_mappings
                WHERE is_active = true
            ),
            to_deactivate AS (SELECT id FROM ranked WHERE rn > 1)
            UPDATE control_plane.vendor_operation_mappings t
            SET is_active = false
            FROM to_deactivate td
            WHERE t.id = td.id;
            GET DIAGNOSTICS r_count = ROW_COUNT;
            IF r_count > 0 THEN
                RAISE NOTICE 'v23: deactivated % duplicate(s) in control_plane.vendor_operation_mappings', r_count;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS control_plane.{IDX_OP_CONTRACTS}")
    op.execute(f"DROP INDEX IF EXISTS control_plane.{IDX_VENDOR_OP_CONTRACTS}")
    op.execute(f"DROP INDEX IF EXISTS control_plane.{IDX_VENDOR_ENDPOINTS}")
    op.execute(f"DROP INDEX IF EXISTS control_plane.{IDX_VENDOR_OP_MAPPINGS}")
