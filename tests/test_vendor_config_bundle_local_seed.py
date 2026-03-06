"""Integration tests for config-bundle with local seed (migrations + seed_local.py).

Requires: DATABASE_URL or DB reachable at localhost:5434.
Run: make local-sync-db (or make local-up) first.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]


def _db_reachable() -> bool:
    try:
        import psycopg2
        url = os.environ.get("DATABASE_URL") or "postgresql://hub:hub@localhost:5434/hub"
        conn = psycopg2.connect(url, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


def _ensure_migrations_and_seed() -> None:
    """Run migrations + seed if DB reachable."""
    url = os.environ.get("DATABASE_URL") or "postgresql://hub:hub@localhost:5434/hub"
    env = {**os.environ, "DATABASE_URL": url}
    subprocess.run(
        [sys.executable, "tooling/scripts/local_db_init.py"],
        cwd=str(_REPO),
        env=env,
        capture_output=True,
        check=True,
    )


@pytest.fixture(scope="module")
def prepared_db() -> None:
    if not _db_reachable():
        pytest.skip("DB not reachable. Run make local-up or ensure Postgres on 5434.")
    _ensure_migrations_and_seed()
    yield


@pytest.mark.skipif(
    os.environ.get("RUN_LOCAL_INTEGRATION_TESTS", "0") != "1" or not _db_reachable(),
    reason="Requires local integration stack. Set RUN_LOCAL_INTEGRATION_TESTS=1 and run 'make local-up' first.",
)
def test_config_bundle_lh001_after_seed(prepared_db: None) -> None:
    """LH001 config-bundle: contracts, supportedOps, allowlist, myOperations ready."""
    os.environ.setdefault(
        "DB_URL",
        os.environ.get("DATABASE_URL", "postgresql://hub:hub@localhost:5434/hub"),
    )
    os.environ.setdefault("RUN_ENV", "local")  # Auth bypass for local API

    from apps.api.local.app import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get(
        "/v1/vendor/config-bundle",
        headers={"x-vendor-code": "LH001"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body.get("vendorCode") == "LH001"

    contracts = body.get("contracts", [])
    assert len(contracts) >= 1
    get_receipt = next((c for c in contracts if c.get("operationCode") == "GET_RECEIPT"), None)
    assert get_receipt is not None
    assert get_receipt.get("canonicalVersion") == "v1"
    req_schema = get_receipt.get("requestSchema") or {}
    assert "txnId" in str(req_schema.get("properties", {}))
    assert req_schema.get("required") == ["txnId"]

    supported = body.get("supportedOperations", [])
    get_receipt_supported = [s for s in supported if s.get("operationCode") == "GET_RECEIPT" and s.get("isActive")]
    assert len(get_receipt_supported) >= 1

    my_allowlist = body.get("myAllowlist", {})
    outbound = my_allowlist.get("outbound", [])
    lh001_lh002 = [r for r in outbound if r.get("sourceVendor") == "LH001" and r.get("targetVendor") == "LH002"]
    assert len(lh001_lh002) >= 1
    assert lh001_lh002[0].get("operation") == "GET_RECEIPT"

    my_ops = body.get("myOperations", {})
    outbound_ops = my_ops.get("outbound", [])
    get_receipt_op = next((o for o in outbound_ops if o.get("operationCode") == "GET_RECEIPT"), None)
    assert get_receipt_op is not None
    assert get_receipt_op.get("partnerVendorCode") == "LH002"
    assert get_receipt_op.get("status") == "ready"


@pytest.mark.skipif(
    os.environ.get("RUN_LOCAL_INTEGRATION_TESTS", "0") != "1" or not _db_reachable(),
    reason="Requires local integration stack. Set RUN_LOCAL_INTEGRATION_TESTS=1 and run 'make local-up' first.",
)
def test_config_bundle_lh002_inbound_support(prepared_db: None) -> None:
    """LH002 config-bundle: GET_RECEIPT with supportsInbound=true."""
    os.environ.setdefault(
        "DB_URL",
        os.environ.get("DATABASE_URL", "postgresql://hub:hub@localhost:5434/hub"),
    )
    os.environ.setdefault("RUN_ENV", "local")  # Auth bypass for local API

    from apps.api.local.app import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get(
        "/v1/vendor/config-bundle",
        headers={"x-vendor-code": "LH002"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body.get("vendorCode") == "LH002"

    supported = body.get("supportedOperations", [])
    get_receipt_supported = [s for s in supported if s.get("operationCode") == "GET_RECEIPT" and s.get("isActive")]
    assert len(get_receipt_supported) >= 1
    assert get_receipt_supported[0].get("supportsInbound") is True
    assert get_receipt_supported[0].get("supportsOutbound") is False
