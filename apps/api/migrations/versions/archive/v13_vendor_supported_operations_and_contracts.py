"""V13: Add vendor_supported_operations and vendor_operation_contracts.

Revision ID: v13
Revises: v12
Create Date: 2025-02-17

- vendor_supported_operations: vendor capability per operation (is_active)
- vendor_operation_contracts: vendor-scoped request/response schemas per operation+version
- Smoke SQL: verify control_plane schema and base tables exist before creating.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v13"
down_revision: str | None = "v12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Smoke: verify control_plane schema and vendors/operations tables exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'control_plane') THEN
                RAISE EXCEPTION 'control_plane schema does not exist - run earlier migrations first';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'control_plane' AND table_name = 'vendors') THEN
                RAISE EXCEPTION 'control_plane.vendors does not exist - run earlier migrations first';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'control_plane' AND table_name = 'operations') THEN
                RAISE EXCEPTION 'control_plane.operations does not exist - run earlier migrations first';
            END IF;
        END $$;
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS control_plane.vendor_supported_operations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_code TEXT NOT NULL REFERENCES control_plane.vendors(vendor_code),
            operation_code TEXT NOT NULL REFERENCES control_plane.operations(operation_code),
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (vendor_code, operation_code)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vendor_supported_ops_vendor_active "
        "ON control_plane.vendor_supported_operations(vendor_code, is_active)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS control_plane.vendor_operation_contracts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_code TEXT NOT NULL REFERENCES control_plane.vendors(vendor_code),
            operation_code TEXT NOT NULL REFERENCES control_plane.operations(operation_code),
            canonical_version TEXT NOT NULL,
            request_schema JSONB NOT NULL,
            response_schema JSONB,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (vendor_code, operation_code, canonical_version)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vendor_operation_contracts_vendor_op_version "
        "ON control_plane.vendor_operation_contracts(vendor_code, operation_code, canonical_version)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS control_plane.vendor_operation_contracts")
    op.execute("DROP TABLE IF EXISTS control_plane.vendor_supported_operations")
