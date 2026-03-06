"""V36: Phase 1.1 - Hub inbound heuristic.

For vendors that are the HUB service (target in admin allowlist rules for an operation),
flip flow_direction from OUTBOUND to INBOUND for those operations.
Assumption: HUB vendor code is 'HUB' or configured hub codes.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v36"
down_revision: str | None = "v35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # For vendor_supported_operations: where vendor is HUB and is target in allowlist for this op
    # → set flow_direction = 'INBOUND'
    op.execute("""
        UPDATE control_plane.vendor_supported_operations s
        SET flow_direction = 'INBOUND'
        WHERE s.flow_direction = 'OUTBOUND'
          AND UPPER(TRIM(s.vendor_code)) = 'HUB'
          AND EXISTS (
            SELECT 1 FROM control_plane.vendor_operation_allowlist a
            WHERE UPPER(TRIM(a.target_vendor_code)) = 'HUB'
              AND UPPER(TRIM(a.operation_code)) = UPPER(TRIM(s.operation_code))
              AND a.rule_scope = 'admin'
          )
    """)

    # For vendor_endpoints: align with supported_ops
    op.execute("""
        UPDATE control_plane.vendor_endpoints e
        SET flow_direction = 'INBOUND'
        WHERE e.flow_direction = 'OUTBOUND'
          AND UPPER(TRIM(e.vendor_code)) = 'HUB'
          AND EXISTS (
            SELECT 1 FROM control_plane.vendor_operation_allowlist a
            WHERE UPPER(TRIM(a.target_vendor_code)) = 'HUB'
              AND UPPER(TRIM(a.operation_code)) = UPPER(TRIM(e.operation_code))
              AND a.rule_scope = 'admin'
          )
    """)

    # vendor_operation_contracts
    op.execute("""
        UPDATE control_plane.vendor_operation_contracts c
        SET flow_direction = 'INBOUND'
        WHERE c.flow_direction = 'OUTBOUND'
          AND UPPER(TRIM(c.vendor_code)) = 'HUB'
          AND EXISTS (
            SELECT 1 FROM control_plane.vendor_operation_allowlist a
            WHERE UPPER(TRIM(a.target_vendor_code)) = 'HUB'
              AND UPPER(TRIM(a.operation_code)) = UPPER(TRIM(c.operation_code))
              AND a.rule_scope = 'admin'
          )
    """)

    # vendor_operation_mappings
    op.execute("""
        UPDATE control_plane.vendor_operation_mappings m
        SET flow_direction = 'INBOUND'
        WHERE m.flow_direction = 'OUTBOUND'
          AND UPPER(TRIM(m.vendor_code)) = 'HUB'
          AND EXISTS (
            SELECT 1 FROM control_plane.vendor_operation_allowlist a
            WHERE UPPER(TRIM(a.target_vendor_code)) = 'HUB'
              AND UPPER(TRIM(a.operation_code)) = UPPER(TRIM(m.operation_code))
              AND a.rule_scope = 'admin'
          )
    """)


def downgrade() -> None:
    # Revert HUB rows back to OUTBOUND
    op.execute("""
        UPDATE control_plane.vendor_supported_operations
        SET flow_direction = 'OUTBOUND'
        WHERE UPPER(TRIM(vendor_code)) = 'HUB' AND flow_direction = 'INBOUND'
    """)
    op.execute("""
        UPDATE control_plane.vendor_endpoints
        SET flow_direction = 'OUTBOUND'
        WHERE UPPER(TRIM(vendor_code)) = 'HUB' AND flow_direction = 'INBOUND'
    """)
    op.execute("""
        UPDATE control_plane.vendor_operation_contracts
        SET flow_direction = 'OUTBOUND'
        WHERE UPPER(TRIM(vendor_code)) = 'HUB' AND flow_direction = 'INBOUND'
    """)
    op.execute("""
        UPDATE control_plane.vendor_operation_mappings
        SET flow_direction = 'OUTBOUND'
        WHERE UPPER(TRIM(vendor_code)) = 'HUB' AND flow_direction = 'INBOUND'
    """)
