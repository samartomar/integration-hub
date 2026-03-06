"""Unit/smoke tests for v24 add_single_active_constraints migration."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# Migration module path (v24 is in archive after baseline consolidation)
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "apps" / "api" / "migrations" / "versions"
V24_PATH = MIGRATIONS_DIR / "archive" / "v24_add_single_active_constraints.py"


def test_v24_migration_module_loads() -> None:
    """Migration module can be imported and has required functions."""
    sys.path.insert(0, str(MIGRATIONS_DIR.parent.parent.parent.parent))  # repo root
    # Load by revision to avoid env.py DATABASE_URL requirement
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "v24_migration",
        V24_PATH,
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert hasattr(mod, "upgrade")
    assert hasattr(mod, "downgrade")
    assert hasattr(mod, "revision")
    assert mod.revision == "v24"
    assert mod.down_revision == "v23"


def test_v24_deactivate_sql_patterns() -> None:
    """Deactivation CTEs use correct PARTITION BY and ORDER BY."""
    path = V24_PATH
    content = path.read_text()

    # operation_contracts: PARTITION BY operation_code, canonical_version
    assert "PARTITION BY operation_code, canonical_version" in content
    assert "ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST" in content

    # vendor_operation_contracts
    assert "PARTITION BY vendor_code, operation_code, canonical_version" in content

    # vendor_endpoints
    assert "PARTITION BY vendor_code, operation_code" in content

    # vendor_operation_mappings
    assert "PARTITION BY vendor_code, operation_code, canonical_version, direction" in content

    # vendor_supported_operations
    assert "vendor_supported_operations" in content
    assert "uq_vendor_supported_operations_active" in content


def test_v24_index_names() -> None:
    """All five partial unique indexes are defined."""
    path = V24_PATH
    content = path.read_text()

    indexes = [
        "uq_operation_contracts_active",
        "uq_vendor_operation_contracts_active",
        "uq_vendor_endpoints_active",
        "uq_vendor_operation_mappings_active",
        "uq_vendor_supported_operations_active",
    ]
    for name in indexes:
        assert name in content, f"Expected index {name}"


def _has_db_config() -> bool:
    """True if DATABASE_URL or DB_SECRET_ARN is set with a valid-looking value.
    Rejects empty, 'None', and invalid placeholders that cause GetSecretValue to fail.
    Smoke script uses DATABASE_URL or DB_SECRET_ARN.
    """

    def _valid_secret_arn(val: str | None) -> bool:
        s = (val or "").strip()
        if not s or s.upper() == "NONE":
            return False
        return s.startswith("arn:aws:secretsmanager:")

    def _valid_db_url(val: str | None) -> bool:
        s = (val or "").strip()
        if not s or s.upper() == "NONE":
            return False
        return s.startswith("postgresql://") or s.startswith("postgres://")

    return _valid_db_url(os.environ.get("DATABASE_URL")) or _valid_secret_arn(
        os.environ.get("DB_SECRET_ARN")
    )


@pytest.mark.skipif(
    not _has_db_config(),
    reason="DATABASE_URL or DB_SECRET_ARN required for integration smoke test",
)
def test_v24_smoke_test_script() -> None:
    """Run smoke test script against live database."""
    script = Path(__file__).resolve().parent.parent / "tooling" / "scripts" / "smoke_test_single_active_constraints.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"Smoke test failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "PASS" in result.stdout or "PASS" in result.stderr
