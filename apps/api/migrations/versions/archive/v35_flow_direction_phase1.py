"""V35: Phase 1 - Add flow_direction to support per-direction config model.

Admin/Vendor model fix - Phase 1 Schema & Migrations.

- Creates flow_direction enum: INBOUND, OUTBOUND, BOTH
- vendor_supported_operations: add canonical_version, flow_direction; UNIQUE(vendor_code, operation_code, canonical_version, flow_direction)
- vendor_operation_allowlist: add flow_direction; default BOTH
- vendor_endpoints: add flow_direction; UNIQUE includes direction
- vendor_operation_contracts: add flow_direction; UNIQUE includes direction
- vendor_operation_mappings: add flow_direction; UNIQUE includes direction

Backfill: Existing rows default to OUTBOUND. Hub heuristic applied in v36.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v35"
down_revision: str | None = "v34"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. vendor_supported_operations: add canonical_version, flow_direction
    op.execute("""
        ALTER TABLE control_plane.vendor_supported_operations
        ADD COLUMN IF NOT EXISTS canonical_version TEXT,
        ADD COLUMN IF NOT EXISTS flow_direction TEXT
    """)
    op.execute("""
        UPDATE control_plane.vendor_supported_operations s
        SET canonical_version = COALESCE(
            (SELECT o.canonical_version FROM control_plane.operations o
             WHERE o.operation_code = s.operation_code AND o.is_active = true
             LIMIT 1), 'v1'),
            flow_direction = COALESCE(flow_direction, 'OUTBOUND')
        WHERE canonical_version IS NULL OR flow_direction IS NULL
    """)
    op.execute("""
        ALTER TABLE control_plane.vendor_supported_operations
        ALTER COLUMN canonical_version SET NOT NULL,
        ALTER COLUMN canonical_version SET DEFAULT 'v1',
        ALTER COLUMN flow_direction SET NOT NULL,
        ALTER COLUMN flow_direction SET DEFAULT 'OUTBOUND'
    """)
    op.execute("""
        ALTER TABLE control_plane.vendor_supported_operations
        ADD CONSTRAINT chk_vendor_supported_ops_flow_direction
        CHECK (flow_direction IN ('INBOUND', 'OUTBOUND'))
    """)

    # Drop old partial unique; add new one including flow_direction
    op.execute("DROP INDEX IF EXISTS control_plane.uq_vendor_supported_operations_active")
    op.execute("""
        CREATE UNIQUE INDEX uq_vendor_supported_operations_active
        ON control_plane.vendor_supported_operations
        (vendor_code, operation_code, canonical_version, flow_direction)
        WHERE is_active = true
    """)

    # 3. vendor_operation_allowlist: add flow_direction
    op.execute("""
        ALTER TABLE control_plane.vendor_operation_allowlist
        ADD COLUMN IF NOT EXISTS flow_direction TEXT
    """)
    op.execute("""
        UPDATE control_plane.vendor_operation_allowlist
        SET flow_direction = COALESCE(flow_direction, 'BOTH')
        WHERE flow_direction IS NULL
    """)
    op.execute("""
        ALTER TABLE control_plane.vendor_operation_allowlist
        ALTER COLUMN flow_direction SET NOT NULL,
        ALTER COLUMN flow_direction SET DEFAULT 'BOTH'
    """)
    op.execute("""
        ALTER TABLE control_plane.vendor_operation_allowlist
        ADD CONSTRAINT chk_allowlist_flow_direction
        CHECK (flow_direction IN ('INBOUND', 'OUTBOUND', 'BOTH'))
    """)

    # Drop allowlist unique to add flow_direction; recreate
    op.execute("DROP INDEX IF EXISTS control_plane.uq_allowlist_source_target_op_scope")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_allowlist_source_target_op_scope_dir
        ON control_plane.vendor_operation_allowlist
        (source_vendor_code, target_vendor_code, operation_code, rule_scope, flow_direction)
    """)

    # 4. vendor_endpoints: add flow_direction
    op.execute("""
        ALTER TABLE control_plane.vendor_endpoints
        ADD COLUMN IF NOT EXISTS flow_direction TEXT
    """)
    op.execute("""
        UPDATE control_plane.vendor_endpoints
        SET flow_direction = COALESCE(flow_direction, 'OUTBOUND')
        WHERE flow_direction IS NULL
    """)
    op.execute("""
        ALTER TABLE control_plane.vendor_endpoints
        ALTER COLUMN flow_direction SET NOT NULL,
        ALTER COLUMN flow_direction SET DEFAULT 'OUTBOUND'
    """)
    op.execute("DROP INDEX IF EXISTS control_plane.uq_vendor_endpoints_active")
    op.execute("""
        CREATE UNIQUE INDEX uq_vendor_endpoints_active
        ON control_plane.vendor_endpoints
        (vendor_code, operation_code, flow_direction)
        WHERE is_active = true
    """)

    # 5. vendor_operation_contracts: add flow_direction
    op.execute("""
        ALTER TABLE control_plane.vendor_operation_contracts
        ADD COLUMN IF NOT EXISTS flow_direction TEXT
    """)
    op.execute("""
        UPDATE control_plane.vendor_operation_contracts
        SET flow_direction = COALESCE(flow_direction, 'OUTBOUND')
        WHERE flow_direction IS NULL
    """)
    op.execute("""
        ALTER TABLE control_plane.vendor_operation_contracts
        ALTER COLUMN flow_direction SET NOT NULL,
        ALTER COLUMN flow_direction SET DEFAULT 'OUTBOUND'
    """)
    op.execute("DROP INDEX IF EXISTS control_plane.uq_vendor_operation_contracts_active")
    op.execute("""
        CREATE UNIQUE INDEX uq_vendor_operation_contracts_active
        ON control_plane.vendor_operation_contracts
        (vendor_code, operation_code, canonical_version, flow_direction)
        WHERE is_active = true
    """)

    # 6. vendor_operation_mappings: add flow_direction (traffic direction, not transform direction)
    op.execute("""
        ALTER TABLE control_plane.vendor_operation_mappings
        ADD COLUMN IF NOT EXISTS flow_direction TEXT
    """)
    op.execute("""
        UPDATE control_plane.vendor_operation_mappings
        SET flow_direction = COALESCE(flow_direction, 'OUTBOUND')
        WHERE flow_direction IS NULL
    """)
    op.execute("""
        ALTER TABLE control_plane.vendor_operation_mappings
        ALTER COLUMN flow_direction SET NOT NULL,
        ALTER COLUMN flow_direction SET DEFAULT 'OUTBOUND'
    """)
    op.execute("DROP INDEX IF EXISTS control_plane.uq_vendor_operation_mappings_active")
    op.execute("""
        CREATE UNIQUE INDEX uq_vendor_operation_mappings_active
        ON control_plane.vendor_operation_mappings
        (vendor_code, operation_code, canonical_version, direction, flow_direction)
        WHERE is_active = true
    """)

    # Indexes for direction-aware queries
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_vendor_supported_ops_flow_direction
        ON control_plane.vendor_supported_operations(vendor_code, flow_direction)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_vendor_endpoints_flow_direction
        ON control_plane.vendor_endpoints(vendor_code, operation_code, flow_direction)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS control_plane.idx_vendor_endpoints_flow_direction")
    op.execute("DROP INDEX IF EXISTS control_plane.idx_vendor_supported_ops_flow_direction")

    # Restore vendor_operation_mappings unique
    op.execute("DROP INDEX IF EXISTS control_plane.uq_vendor_operation_mappings_active")
    op.execute("""
        CREATE UNIQUE INDEX uq_vendor_operation_mappings_active
        ON control_plane.vendor_operation_mappings
        (vendor_code, operation_code, canonical_version, direction)
        WHERE is_active = true
    """)
    op.execute("ALTER TABLE control_plane.vendor_operation_mappings DROP COLUMN IF EXISTS flow_direction")

    # Restore vendor_operation_contracts unique
    op.execute("DROP INDEX IF EXISTS control_plane.uq_vendor_operation_contracts_active")
    op.execute("""
        CREATE UNIQUE INDEX uq_vendor_operation_contracts_active
        ON control_plane.vendor_operation_contracts
        (vendor_code, operation_code, canonical_version)
        WHERE is_active = true
    """)
    op.execute("ALTER TABLE control_plane.vendor_operation_contracts DROP COLUMN IF EXISTS flow_direction")

    # Restore vendor_endpoints unique
    op.execute("DROP INDEX IF EXISTS control_plane.uq_vendor_endpoints_active")
    op.execute("""
        CREATE UNIQUE INDEX uq_vendor_endpoints_active
        ON control_plane.vendor_endpoints
        (vendor_code, operation_code)
        WHERE is_active = true
    """)
    op.execute("ALTER TABLE control_plane.vendor_endpoints DROP COLUMN IF EXISTS flow_direction")

    # Restore allowlist unique
    op.execute("DROP INDEX IF EXISTS control_plane.uq_allowlist_source_target_op_scope_dir")
    op.execute("ALTER TABLE control_plane.vendor_operation_allowlist DROP CONSTRAINT IF EXISTS chk_allowlist_flow_direction")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_allowlist_source_target_op_scope
        ON control_plane.vendor_operation_allowlist
        (source_vendor_code, target_vendor_code, operation_code, rule_scope)
    """)
    op.execute("ALTER TABLE control_plane.vendor_operation_allowlist DROP COLUMN IF EXISTS flow_direction")

    # Restore vendor_supported_operations unique
    op.execute("DROP INDEX IF EXISTS control_plane.uq_vendor_supported_operations_active")
    op.execute("""
        CREATE UNIQUE INDEX uq_vendor_supported_operations_active
        ON control_plane.vendor_supported_operations
        (vendor_code, operation_code)
        WHERE is_active = true
    """)
    op.execute("ALTER TABLE control_plane.vendor_supported_operations DROP CONSTRAINT IF EXISTS chk_vendor_supported_ops_flow_direction")
    op.execute("ALTER TABLE control_plane.vendor_supported_operations DROP COLUMN IF EXISTS flow_direction")
    op.execute("ALTER TABLE control_plane.vendor_supported_operations DROP COLUMN IF EXISTS canonical_version")
