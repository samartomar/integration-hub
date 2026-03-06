#!/usr/bin/env python3
"""
Smoke test for single-active-constraints behavior (vendor_operation_contracts).

Verifies that:
1. Duplicate active rows are deactivated (keeps newest by updated_at/created_at)
2. Partial unique index uq_vendor_operation_contracts_active is present

Works with current migration chain (baseline -> v46 -> v47 -> v48 -> v49).
Uses vendor_operation_contracts (no full UNIQUE) so we can insert duplicates.

Requires: DATABASE_URL (e.g. postgresql://user:pass@localhost:5432/integrationhub)

Usage:
  DATABASE_URL=postgresql://... python tooling/scripts/smoke_test_single_active_constraints.py

Or with SSM port-forward + DB_SECRET_ARN:
  .\\tooling\\scripts\\run-ssm-port-forward.ps1
  $env:DB_SECRET_ARN = "arn:aws:secretsmanager:..."
  python tooling/scripts/smoke_test_single_active_constraints.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[1]
TEST_VENDOR = "SMOKE_VENDOR"
TEST_OP = "SMOKE_TEST_OP"


def _get_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    secret_arn = os.environ.get("DB_SECRET_ARN")
    if not secret_arn:
        raise SystemExit(
            "Set DATABASE_URL or DB_SECRET_ARN. "
            "With DB_SECRET_ARN, start SSM port-forward first."
        )
    result = subprocess.run(
        [
            "aws", "secretsmanager", "get-secret-value",
            "--secret-id", secret_arn,
            "--query", "SecretString", "--output", "text",
        ],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"Failed to fetch secret: {result.stderr}")
    secret = json.loads(result.stdout)
    pw = urllib.parse.quote(str(secret["password"]), safe="")
    user = secret.get("username") or secret.get("user", "clusteradmin")
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    dbname = secret.get("dbname") or secret.get("database", "integrationhub")
    return f"postgresql://{user}:{pw}@{host}:{port}/{dbname}"


def _deactivate_duplicates_vendor_operation_contracts(cur) -> None:
    """Deactivate duplicate active rows, keeping newest by updated_at/created_at."""
    cur.execute("""
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY vendor_code, operation_code, canonical_version, flow_direction
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


def main() -> int:
    url = _get_url()
    print("Connecting to database...")

    with psycopg2.connect(url) as conn:
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            rev = None
            cur.execute("SELECT version_num FROM alembic_version")
            row = cur.fetchone()
            if row:
                rev = row["version_num"]
            print(f"Current revision: {rev}")

            # Drop the partial unique index so we can insert duplicate active rows
            cur.execute("DROP INDEX IF EXISTS control_plane.uq_vendor_operation_contracts_active")
            conn.commit()

            # Ensure vendor and operation exist
            cur.execute(
                f"""
                INSERT INTO control_plane.vendors (vendor_code, vendor_name)
                VALUES ('{TEST_VENDOR}', 'Smoke test vendor')
                ON CONFLICT (vendor_code) DO NOTHING
                """
            )
            cur.execute(
                f"""
                INSERT INTO control_plane.operations (operation_code, description, canonical_version, is_active)
                VALUES ('{TEST_OP}', 'Smoke test', 'v1', true)
                ON CONFLICT (operation_code) DO NOTHING
                """
            )
            conn.commit()

            # Insert duplicate active rows into vendor_operation_contracts
            cur.execute(
                f"""
                INSERT INTO control_plane.vendor_operation_contracts
                (vendor_code, operation_code, canonical_version, flow_direction, request_schema, response_schema, is_active, created_at, updated_at)
                VALUES
                ('{TEST_VENDOR}', '{TEST_OP}', 'v1', 'OUTBOUND', '{{"type":"object"}}', '{{"type":"object"}}', true, now() - interval '2 minutes', now() - interval '2 minutes'),
                ('{TEST_VENDOR}', '{TEST_OP}', 'v1', 'OUTBOUND', '{{"type":"object"}}', '{{"type":"object"}}', true, now() - interval '1 minute', now() - interval '1 minute'),
                ('{TEST_VENDOR}', '{TEST_OP}', 'v1', 'OUTBOUND', '{{"type":"object"}}', '{{"type":"object"}}', true, now(), now())
                """
            )
            conn.commit()

            # Verify duplicates exist
            cur.execute(
                f"""
                SELECT id, vendor_code, operation_code, canonical_version, flow_direction, is_active, updated_at
                FROM control_plane.vendor_operation_contracts
                WHERE vendor_code = '{TEST_VENDOR}' AND operation_code = '{TEST_OP}'
                ORDER BY updated_at DESC
                """
            )
            rows_before = cur.fetchall()
            active_before = sum(1 for r in rows_before if r["is_active"])
            print(f"  vendor_operation_contracts: {len(rows_before)} rows, {active_before} active (expect 3)")

            conn.commit()

        except Exception as e:
            conn.rollback()
            raise SystemExit(f"Setup failed: {e}") from e

    # Run deactivation (same logic as v24 / baseline single-active constraints)
    print("Running deactivation (keep newest, deactivate older duplicates)...")
    with psycopg2.connect(url) as conn:
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)
        _deactivate_duplicates_vendor_operation_contracts(cur)
        conn.commit()

    # Recreate the partial unique index
    print("Recreating uq_vendor_operation_contracts_active index...")
    with psycopg2.connect(url) as conn:
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_vendor_operation_contracts_active
            ON control_plane.vendor_operation_contracts(vendor_code, operation_code, canonical_version, flow_direction)
            WHERE is_active = true
        """)
        conn.commit()

    with psycopg2.connect(url) as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            f"""
            SELECT id, vendor_code, operation_code, canonical_version, flow_direction, is_active, updated_at
            FROM control_plane.vendor_operation_contracts
            WHERE vendor_code = '{TEST_VENDOR}' AND operation_code = '{TEST_OP}'
            ORDER BY updated_at DESC
            """
        )
        rows_after = cur.fetchall()
        active_after = sum(1 for r in rows_after if r["is_active"])
        print(f"  After deactivation: {len(rows_after)} rows, {active_after} active (expect 1)")

        if active_after != 1:
            raise SystemExit(f"FAIL: expected 1 active row, got {active_after}")

        # Verify index exists
        cur.execute(
            """
            SELECT indexname FROM pg_indexes
            WHERE schemaname = 'control_plane' AND indexname = 'uq_vendor_operation_contracts_active'
            """
        )
        if cur.fetchone() is None:
            raise SystemExit("FAIL: index uq_vendor_operation_contracts_active not found")

        # Cleanup smoke test data
        cur.execute(
            f"DELETE FROM control_plane.vendor_operation_contracts WHERE vendor_code = '{TEST_VENDOR}' AND operation_code = '{TEST_OP}'"
        )
        cur.execute(f"DELETE FROM control_plane.operations WHERE operation_code = '{TEST_OP}'")
        cur.execute(f"DELETE FROM control_plane.vendors WHERE vendor_code = '{TEST_VENDOR}'")
        conn.commit()

    print("PASS: single-active-constraints smoke test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
