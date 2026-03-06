"""V24: Add single active row constraints (add_single_active_constraints).

Revision ID: v24
Revises: v23
Create Date: 2025-02-19

For each target table in control_plane:
1) Clean duplicates: keep newest by updated_at (or created_at), deactivate older rows
2) Add partial unique index WHERE is_active = true

Target tables:
- operation_contracts(operation_code, canonical_version, is_active)
- vendor_operation_contracts(vendor_code, operation_code, canonical_version, is_active)
- vendor_endpoints(vendor_code, operation_code, is_active)
- vendor_operation_mappings(vendor_code, operation_code, canonical_version, direction, is_active)
- vendor_supported_operations(vendor_code, operation_code, is_active)
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "v24"
down_revision: str | None = "v23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop v23 indexes if they exist (we replace with uq_*_active naming)
    op.execute("DROP INDEX IF EXISTS control_plane.uq_operation_contracts_single_active")
    op.execute("DROP INDEX IF EXISTS control_plane.uq_vendor_operation_contracts_single_active")
    op.execute("DROP INDEX IF EXISTS control_plane.uq_vendor_endpoints_single_active")
    op.execute("DROP INDEX IF EXISTS control_plane.uq_vendor_operation_mappings_single_active")

    # -------------------------------------------------------------------------
    # 1) operation_contracts
    # -------------------------------------------------------------------------
    _deactivate_duplicates_operation_contracts()
    op.create_index(
        "uq_operation_contracts_active",
        "operation_contracts",
        ["operation_code", "canonical_version"],
        unique=True,
        schema="control_plane",
        postgresql_where=sa.text("is_active = true"),
    )

    # -------------------------------------------------------------------------
    # 2) vendor_operation_contracts
    # -------------------------------------------------------------------------
    _deactivate_duplicates_vendor_operation_contracts()
    op.create_index(
        "uq_vendor_operation_contracts_active",
        "vendor_operation_contracts",
        ["vendor_code", "operation_code", "canonical_version"],
        unique=True,
        schema="control_plane",
        postgresql_where=sa.text("is_active = true"),
    )

    # -------------------------------------------------------------------------
    # 3) vendor_endpoints
    # -------------------------------------------------------------------------
    _deactivate_duplicates_vendor_endpoints()
    op.create_index(
        "uq_vendor_endpoints_active",
        "vendor_endpoints",
        ["vendor_code", "operation_code"],
        unique=True,
        schema="control_plane",
        postgresql_where=sa.text("is_active = true"),
    )

    # -------------------------------------------------------------------------
    # 4) vendor_operation_mappings
    # -------------------------------------------------------------------------
    _deactivate_duplicates_vendor_operation_mappings()
    op.create_index(
        "uq_vendor_operation_mappings_active",
        "vendor_operation_mappings",
        ["vendor_code", "operation_code", "canonical_version", "direction"],
        unique=True,
        schema="control_plane",
        postgresql_where=sa.text("is_active = true"),
    )

    # -------------------------------------------------------------------------
    # 5) vendor_supported_operations
    # -------------------------------------------------------------------------
    _deactivate_duplicates_vendor_supported_operations()
    op.create_index(
        "uq_vendor_supported_operations_active",
        "vendor_supported_operations",
        ["vendor_code", "operation_code"],
        unique=True,
        schema="control_plane",
        postgresql_where=sa.text("is_active = true"),
    )


def _deactivate_duplicates_operation_contracts() -> None:
    op.execute("""
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY operation_code, canonical_version
                       ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id
                   ) AS rn
            FROM control_plane.operation_contracts
            WHERE is_active = true
        )
        UPDATE control_plane.operation_contracts oc
        SET is_active = false
        FROM ranked r
        WHERE oc.id = r.id AND r.rn > 1
    """)


def _deactivate_duplicates_vendor_operation_contracts() -> None:
    op.execute("""
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY vendor_code, operation_code, canonical_version
                       ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id
                   ) AS rn
            FROM control_plane.vendor_operation_contracts
            WHERE is_active = true
        )
        UPDATE control_plane.vendor_operation_contracts oc
        SET is_active = false
        FROM ranked r
        WHERE oc.id = r.id AND r.rn > 1
    """)


def _deactivate_duplicates_vendor_endpoints() -> None:
    op.execute("""
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY vendor_code, operation_code
                       ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id
                   ) AS rn
            FROM control_plane.vendor_endpoints
            WHERE is_active = true
        )
        UPDATE control_plane.vendor_endpoints e
        SET is_active = false
        FROM ranked r
        WHERE e.id = r.id AND r.rn > 1
    """)


def _deactivate_duplicates_vendor_operation_mappings() -> None:
    op.execute("""
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY vendor_code, operation_code, canonical_version, direction
                       ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id
                   ) AS rn
            FROM control_plane.vendor_operation_mappings
            WHERE is_active = true
        )
        UPDATE control_plane.vendor_operation_mappings m
        SET is_active = false
        FROM ranked r
        WHERE m.id = r.id AND r.rn > 1
    """)


def _deactivate_duplicates_vendor_supported_operations() -> None:
    op.execute("""
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY vendor_code, operation_code
                       ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id
                   ) AS rn
            FROM control_plane.vendor_supported_operations
            WHERE is_active = true
        )
        UPDATE control_plane.vendor_supported_operations s
        SET is_active = false
        FROM ranked r
        WHERE s.id = r.id AND r.rn > 1
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS control_plane.uq_vendor_supported_operations_active")
    op.execute("DROP INDEX IF EXISTS control_plane.uq_vendor_operation_mappings_active")
    op.execute("DROP INDEX IF EXISTS control_plane.uq_vendor_endpoints_active")
    op.execute("DROP INDEX IF EXISTS control_plane.uq_vendor_operation_contracts_active")
    op.execute("DROP INDEX IF EXISTS control_plane.uq_operation_contracts_active")
