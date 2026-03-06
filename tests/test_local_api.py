"""Integration-style tests for local HTTP API (no AWS)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Import app after ensuring path (tests run from repo root)
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _ensure_migrations_and_seed() -> None:
    """Run migrations + seed so DB has latest seed (including VERIFIED endpoint)."""
    url = os.environ.get("DATABASE_URL") or "postgresql://hub:hub@localhost:5434/hub"
    env = {**os.environ, "DATABASE_URL": url}
    subprocess.run(
        [sys.executable, "tooling/scripts/local_db_init.py"],
        cwd=str(_REPO),
        env=env,
        capture_output=True,
        check=True,
    )


def _db_reachable() -> bool:
    """True if local Postgres is reachable (e.g. after make local-up)."""
    try:
        import psycopg2

        url = os.environ.get("DATABASE_URL") or "postgresql://hub:hub@localhost:5434/hub"
        conn = psycopg2.connect(url, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    os.environ.get("RUN_LOCAL_INTEGRATION_TESTS", "0") != "1" or not _db_reachable(),
    reason="Requires local integration stack. Set RUN_LOCAL_INTEGRATION_TESTS=1 and run 'make local-up' first.",
)
def test_local_api_execute_with_db() -> None:
    """
    POST /v1/integrations/execute with real handler and local Postgres.
    Requires: make local-up (DB + hub seed with LH001, LH002, local-dev key).
    Mocks downstream HTTP so external provider endpoint does not need to be reachable.
    """
    _ensure_migrations_and_seed()
    os.environ.setdefault("DB_URL", os.environ.get("DATABASE_URL", "postgresql://hub:hub@localhost:5434/hub"))
    os.environ.setdefault("RUN_ENV", "local")  # Auth bypass for local API (JWT path)

    from apps.api.local.app import app

    # Mock requests.request so downstream call succeeds regardless of endpoint reachability.
    with patch("requests.request") as mock_request:
        mock_request.return_value = MagicMock(
            status_code=200,
            headers={"Content-Type": "application/json"},
            json=lambda: {"status": "OK", "receiptId": "R-tx-integration-test"},
        )
        client = TestClient(app)
        resp = client.post(
            "/v1/integrations/execute",
            headers={"Authorization": "Bearer local-dev", "Content-Type": "application/json"},
            json={
                "targetVendor": "LH002",
                "operation": "GET_RECEIPT",
                "value": {"txnId": "tx-integration-test"},
            },
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "transactionId" in data
    assert "correlationId" in data
    status = data.get("status") or data.get("responseBody", {}).get("status")
    assert status in ("completed", "COMPLETED")


def test_local_api_health() -> None:
    """GET /health returns 200 without any AWS or DB."""
    from apps.api.local.app import app

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"
    assert data.get("mode") == "local"


def test_local_api_execute_wired() -> None:
    """
    POST /v1/execute with valid mock: routing handler is invoked and response
    is converted to HTTP. Uses mocked handler to avoid DB/AWS.
    """
    from apps.api.local import app as app_module
    from apps.api.local.app import app

    # Stub the routing handler to return a fixed 200 (tests HTTP wiring, not routing logic)
    stub_response = {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {
                "transactionId": "tx-test",
                "correlationId": "corr-test",
                "status": "completed",
                "responseBody": {"receiptId": "R-test"},
            }
        ),
    }

    def fake_handler(event: dict, context: object) -> dict:
        assert event.get("path") in ("/v1/execute", "/v1/integrations/execute")
        assert event.get("httpMethod") == "POST"
        return stub_response

    with patch.object(app_module, "_get_routing_handler", return_value=fake_handler):
        client = TestClient(app)
        resp = client.post(
            "/v1/execute",
            headers={"Authorization": "Bearer local-dev", "Content-Type": "application/json"},
            json={
                "sourceVendor": "LH001",
                "targetVendor": "LH002",
                "operation": "GET_RECEIPT",
                "value": {"txnId": "tx-1"},
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("transactionId") == "tx-test"
    assert data.get("status") == "completed"


def test_local_api_vendor_path_wired() -> None:
    """GET /v1/vendor/... invokes vendor_registry handler (mocked)."""
    from apps.api.local import app as app_module
    from apps.api.local.app import app

    stub_response = {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"items": [], "nextCursor": None}),
    }

    def fake_vendor_handler(event: dict, context: object) -> dict:
        assert "vendor" in (event.get("path") or "")
        return stub_response

    with patch.object(app_module, "_get_vendor_handler", return_value=fake_vendor_handler):
        client = TestClient(app)
        resp = client.get(
            "/v1/vendor/flows/GET_RECEIPT/v1",
            headers={"Authorization": "Bearer local-dev"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
