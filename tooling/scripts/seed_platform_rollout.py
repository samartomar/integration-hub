#!/usr/bin/env python3
"""Seed Journey Mode platform rollout data only (idempotent)."""

from __future__ import annotations

import os

import psycopg2
from psycopg2.extras import RealDictCursor


def _build_db_url() -> str:
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    host = os.getenv("PGHOST", "localhost")
    port = os.getenv("PGPORT", "5434")
    user = os.getenv("PGUSER", "hub")
    password = os.getenv("PGPASSWORD", "hub")
    db = os.getenv("PGDATABASE", "hub")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


FEATURES = [
    "home_welcome",
    "registry_basic",
    "execute_test",
    "audit_view",
    "flow_builder",
    "mappings_ui",
    "governance_allowlist",
    "approvals",
    "replay_console",
    "ai_formatter_ui",
    "usage_billing_ui",
]

PHASES = [
    ("PHASE_0", "Foundation", "Initial demo foundation"),
    ("PHASE_1", "Build", "Enable build-focused capabilities"),
    ("PHASE_2", "Govern", "Add governance and approvals"),
    ("PHASE_3", "Operate", "Enable runtime operations tooling"),
    ("PHASE_4", "Optimize", "Enable optimization capabilities"),
]

PHASE_FEATURES = {
    "PHASE_0": {"home_welcome", "registry_basic", "execute_test", "audit_view"},
    "PHASE_1": {
        "home_welcome",
        "registry_basic",
        "execute_test",
        "audit_view",
        "flow_builder",
        "mappings_ui",
    },
    "PHASE_2": {
        "home_welcome",
        "registry_basic",
        "execute_test",
        "audit_view",
        "flow_builder",
        "mappings_ui",
        "governance_allowlist",
        "approvals",
    },
    "PHASE_3": {
        "home_welcome",
        "registry_basic",
        "execute_test",
        "audit_view",
        "flow_builder",
        "mappings_ui",
        "governance_allowlist",
        "approvals",
        "replay_console",
    },
    "PHASE_4": {
        "home_welcome",
        "registry_basic",
        "execute_test",
        "audit_view",
        "flow_builder",
        "mappings_ui",
        "governance_allowlist",
        "approvals",
        "replay_console",
        "ai_formatter_ui",
        "usage_billing_ui",
    },
}


def main() -> None:
    db_url = _build_db_url()
    print(f"[seed_platform_rollout] Connecting to DB: {db_url}")
    conn = psycopg2.connect(db_url)
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                for code in FEATURES:
                    cur.execute(
                        """
                        INSERT INTO control_plane.platform_features (
                            feature_code, is_enabled, description
                        )
                        VALUES (%s, NULL, NULL)
                        ON CONFLICT (feature_code)
                        DO UPDATE SET
                            is_enabled = EXCLUDED.is_enabled,
                            description = EXCLUDED.description,
                            updated_at = now()
                        """,
                        (code,),
                    )

                for phase_code, phase_name, description in PHASES:
                    cur.execute(
                        """
                        INSERT INTO control_plane.platform_phases (
                            phase_code, phase_name, description
                        )
                        VALUES (%s, %s, %s)
                        ON CONFLICT (phase_code)
                        DO UPDATE SET
                            phase_name = EXCLUDED.phase_name,
                            description = EXCLUDED.description,
                            updated_at = now()
                        """,
                        (phase_code, phase_name, description),
                    )

                for phase_code, feature_codes in PHASE_FEATURES.items():
                    for feature_code in sorted(feature_codes):
                        cur.execute(
                            """
                            INSERT INTO control_plane.platform_phase_features (
                                phase_code, feature_code, is_enabled
                            )
                            VALUES (%s, %s, true)
                            ON CONFLICT (phase_code, feature_code)
                            DO UPDATE SET
                                is_enabled = EXCLUDED.is_enabled
                            """,
                            (phase_code, feature_code),
                        )

                cur.execute(
                    """
                    INSERT INTO control_plane.platform_settings (
                        settings_key, settings_value
                    )
                    VALUES ('CURRENT_PHASE', 'PHASE_0')
                    ON CONFLICT (settings_key)
                    DO UPDATE SET
                        settings_value = EXCLUDED.settings_value,
                        updated_at = now()
                    """
                )
        print("[seed_platform_rollout] Seed complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
