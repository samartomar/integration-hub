"""V33: Add rule_scope to vendor_operation_allowlist.

Distinguishes admin-defined eligibility (who *could* talk) from vendor opt-in rules.
- admin: Created by Admin portal, defines upper bound of permitted traffic.
- vendor: Created by Vendor portal via Access control, actual opt-in for that licensee.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "v33"
down_revision: str | None = "v32"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE control_plane.vendor_operation_allowlist
        ADD COLUMN IF NOT EXISTS rule_scope TEXT DEFAULT 'admin'
    """)
    op.execute("""
        UPDATE control_plane.vendor_operation_allowlist
        SET rule_scope = 'admin'
        WHERE rule_scope IS NULL
    """)
    op.execute("""
        ALTER TABLE control_plane.vendor_operation_allowlist
        ALTER COLUMN rule_scope SET NOT NULL,
        ALTER COLUMN rule_scope SET DEFAULT 'admin'
    """)
    op.execute(
        "COMMENT ON COLUMN control_plane.vendor_operation_allowlist.rule_scope IS "
        "'admin: hub-defined eligibility; vendor: licensee opt-in from Access control. Default admin.'"
    )
    # Drop existing unique on (source, target, op) to allow same combo with different rule_scope
    op.execute("""
        DO $$
        DECLARE
            cname TEXT;
        BEGIN
            SELECT tc.constraint_name INTO cname
            FROM information_schema.table_constraints tc
            WHERE tc.table_schema = 'control_plane'
              AND tc.table_name = 'vendor_operation_allowlist'
              AND tc.constraint_type = 'UNIQUE';
            IF cname IS NOT NULL THEN
                EXECUTE format('ALTER TABLE control_plane.vendor_operation_allowlist DROP CONSTRAINT %I', cname);
            END IF;
        END $$
    """)
    # New unique: (source, target, op, rule_scope) so admin and vendor rows can coexist
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_allowlist_source_target_op_scope
        ON control_plane.vendor_operation_allowlist
        (source_vendor_code, target_vendor_code, operation_code, rule_scope)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS control_plane.uq_allowlist_source_target_op_scope")
    op.execute("""
        ALTER TABLE control_plane.vendor_operation_allowlist
        ADD CONSTRAINT vendor_operation_allowlist_src_tgt_op_key
        UNIQUE (source_vendor_code, target_vendor_code, operation_code)
    """)
    op.execute("""
        ALTER TABLE control_plane.vendor_operation_allowlist
        DROP COLUMN IF EXISTS rule_scope
    """)
