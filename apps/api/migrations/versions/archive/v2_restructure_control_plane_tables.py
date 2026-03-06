"""V2: Restructure control_plane tables to match vendor/operation code model.

Revision ID: v2
Revises: v1
Create Date: 2025-02-12

Tables support:
  INSERT INTO control_plane.vendors (vendor_code, vendor_name) VALUES (...) ON CONFLICT (vendor_code) DO NOTHING;
  INSERT INTO control_plane.operations (operation_code, description, canonical_version, is_async_capable, is_active) ...;
  INSERT INTO control_plane.vendor_operation_allowlist (source_vendor_code, target_vendor_code, operation_code) ...;
  INSERT INTO control_plane.vendor_endpoints (vendor_code, operation_code, url, http_method, payload_format, timeout_ms, is_active) ...;
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v2"
down_revision: str | None = "v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop in reverse dependency order
    op.execute("DROP TABLE IF EXISTS control_plane.vendor_operation_allowlist")
    op.execute("DROP TABLE IF EXISTS control_plane.vendor_endpoints")
    op.execute("DROP TABLE IF EXISTS control_plane.operations")
    op.execute("DROP TABLE IF EXISTS control_plane.vendors")

    op.execute("""
        CREATE TABLE control_plane.vendors (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_code TEXT UNIQUE NOT NULL,
            vendor_name TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vendors_vendor_code "
        "ON control_plane.vendors(vendor_code)"
    )

    op.execute("""
        CREATE TABLE control_plane.operations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            operation_code TEXT UNIQUE NOT NULL,
            description TEXT,
            canonical_version TEXT,
            is_async_capable BOOLEAN DEFAULT true,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_operations_operation_code "
        "ON control_plane.operations(operation_code)"
    )

    op.execute("""
        CREATE TABLE control_plane.vendor_operation_allowlist (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_vendor_code TEXT NOT NULL,
            target_vendor_code TEXT NOT NULL,
            operation_code TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE(source_vendor_code, target_vendor_code, operation_code)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vendor_operation_allowlist_source_target_op "
        "ON control_plane.vendor_operation_allowlist(source_vendor_code, target_vendor_code, operation_code)"
    )

    op.execute("""
        CREATE TABLE control_plane.vendor_endpoints (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_code TEXT NOT NULL,
            operation_code TEXT NOT NULL,
            url TEXT NOT NULL,
            http_method TEXT,
            payload_format TEXT,
            timeout_ms INTEGER,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE(vendor_code, operation_code)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vendor_endpoints_vendor_operation "
        "ON control_plane.vendor_endpoints(vendor_code, operation_code)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS control_plane.vendor_endpoints")
    op.execute("DROP TABLE IF EXISTS control_plane.vendor_operation_allowlist")
    op.execute("DROP TABLE IF EXISTS control_plane.operations")
    op.execute("DROP TABLE IF EXISTS control_plane.vendors")

    # Restore V1 structure
    op.execute("""
        CREATE TABLE control_plane.vendors (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_code TEXT UNIQUE,
            name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE control_plane.operations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE control_plane.vendor_endpoints (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_id UUID NOT NULL REFERENCES control_plane.vendors(id) ON DELETE CASCADE,
            endpoint_type TEXT NOT NULL,
            url TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE control_plane.vendor_operation_allowlist (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_id UUID NOT NULL REFERENCES control_plane.vendors(id) ON DELETE CASCADE,
            operation_id UUID NOT NULL REFERENCES control_plane.operations(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE(vendor_id, operation_id)
        )
    """)
