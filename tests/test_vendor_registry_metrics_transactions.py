"""Unit tests for Vendor Registry Lambda - metrics overview and transactions endpoints."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from vendor_registry_lambda import handler  # noqa: E402
from vendor_registry_jwt import add_jwt_auth  # noqa: E402


def _event(
    path: str = "/v1/vendor/metrics/overview",
    method: str = "GET",
    query: dict | None = None,
) -> dict:
    """Build event. path must not include query string (API Gateway separates them)."""
    return {
        "path": path,
        "rawPath": path,
        "httpMethod": method,
        "pathParameters": {},
        "queryStringParameters": query or {},
        "requestContext": {"http": {"method": method}, "requestId": "test-req-id"},
        "headers": {},
    }


# --- Metrics Overview ---


@patch("vendor_registry_lambda._query_metrics_overview")
@patch("vendor_registry_lambda._get_connection")
def test_metrics_overview_aggregation_by_status_and_operation(
    mock_conn_ctx: MagicMock,
    mock_query: MagicMock,
) -> None:
    """Metrics overview returns correct totals, byStatus, byOperation."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    mock_query.return_value = {
        "totals": {"count": 42, "completed": 30, "failed": 12},
        "byStatus": [
            {"status": "completed", "count": 30},
            {"status": "validation_failed", "count": 8},
            {"status": "downstream_error", "count": 4},
        ],
        "byOperation": [
            {"operation": "GET_RECEIPT", "count": 40, "failed": 10},
            {"operation": "LIST_REPOS", "count": 2, "failed": 2},
        ],
        "timeseries": [
            {"bucket": "2026-02-19T10:00:00Z", "count": 5, "failed": 1},
            {"bucket": "2026-02-19T11:00:00Z", "count": 8, "failed": 2},
        ],
    }

    event = _event(
        "/v1/vendor/metrics/overview",
        "GET",
        {"from": "2026-02-19T00:00:00Z", "to": "2026-02-20T00:00:00Z"},
    )
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["totals"]["count"] == 42
    assert body["totals"]["completed"] == 30
    assert body["totals"]["failed"] == 12
    assert len(body["byStatus"]) == 3
    assert body["byStatus"][0]["status"] == "completed" and body["byStatus"][0]["count"] == 30
    assert len(body["byOperation"]) == 2
    assert body["byOperation"][0]["operation"] == "GET_RECEIPT" and body["byOperation"][0]["failed"] == 10
    assert len(body["timeseries"]) == 2
    mock_query.assert_called_once()


@patch("vendor_registry_lambda._get_connection")
def test_metrics_overview_missing_from_to_returns_400(
    mock_conn_ctx: MagicMock,
) -> None:
    """Metrics overview without from/to returns VALIDATION_ERROR."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    event = _event("/v1/vendor/metrics/overview", "GET", {})
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "VALIDATION_ERROR"


# --- Transactions List ---


@patch("vendor_registry_lambda._query_vendor_transactions")
@patch("vendor_registry_lambda._get_connection")
def test_transactions_list_direction_filter(
    mock_conn_ctx: MagicMock,
    mock_query: MagicMock,
) -> None:
    """Transactions list with direction=outbound filters by source_vendor."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    mock_query.return_value = (
        [
            {
                "id": "uuid-1",
                "transaction_id": "tx-1",
                "correlation_id": "corr-1",
                "source_vendor": "LH001",
                "target_vendor": "LH002",
                "operation": "GET_RECEIPT",
                "status": "completed",
                "created_at": "2026-02-19T10:00:00",
            },
        ],
        None,
    )

    event = _event(
        "/v1/vendor/transactions",
        "GET",
        {
            "from": "2026-02-19T00:00:00Z",
            "to": "2026-02-20T00:00:00Z",
            "direction": "outbound",
        },
    )
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["count"] == 1
    tx0 = body["transactions"][0]
    assert tx0.get("sourceVendor") == "LH001" or tx0.get("source_vendor") == "LH001"
    call_args = mock_query.call_args[0]
    assert call_args[2] == "outbound"  # direction
    assert call_args[1] == "LH001"  # vendor_code


@patch("vendor_registry_lambda._query_vendor_transactions")
@patch("vendor_registry_lambda._get_connection")
def test_transactions_list_pagination_next_cursor(
    mock_conn_ctx: MagicMock,
    mock_query: MagicMock,
) -> None:
    """Transactions list returns nextCursor when more results exist."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    mock_query.return_value = (
        [
            {
                "id": "u1",
                "transaction_id": "tx-1",
                "correlation_id": "c1",
                "source_vendor": "LH001",
                "target_vendor": "LH002",
                "operation": "GET_RECEIPT",
                "status": "completed",
                "created_at": "2026-02-19T10:00:00",
            },
        ],
        "cursor-abc",
    )

    event = _event(
        "/v1/vendor/transactions",
        "GET",
        {"from": "2026-02-19T00:00:00Z", "to": "2026-02-20T00:00:00Z", "limit": "10"},
    )
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "nextCursor" in body
    assert body["nextCursor"] == "cursor-abc"
    assert body["count"] == 1


# --- Transaction Detail ---


@patch("vendor_registry_lambda._get_transaction_by_id_vendor")
@patch("vendor_registry_lambda._get_connection")
def test_transaction_detail_vendor_allowed_when_source(
    mock_conn_ctx: MagicMock,
    mock_get: MagicMock,
) -> None:
    """Vendor can see transaction when they are source."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    mock_get.return_value = {
        "transaction_id": "tx-1",
        "correlation_id": "c1",
        "source_vendor": "LH001",
        "target_vendor": "LH002",
        "operation": "GET_RECEIPT",
        "status": "completed",
        "created_at": "2026-02-19T10:00:00",
    }

    event = _event("/v1/vendor/transactions/tx-1", "GET")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["transactionId"] == "tx-1"
    assert body["sourceVendor"] == "LH001"
    mock_get.assert_called_once_with(mock_conn, "tx-1", "LH001")


@patch("vendor_registry_lambda._get_transaction_by_id_vendor")
@patch("vendor_registry_lambda._get_connection")
def test_transaction_detail_vendor_allowed_when_target(
    mock_conn_ctx: MagicMock,
    mock_get: MagicMock,
) -> None:
    """Vendor can see transaction when they are target."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    mock_get.return_value = {
        "transaction_id": "tx-2",
        "correlation_id": "c2",
        "source_vendor": "GITHUB",
        "target_vendor": "LH001",
        "operation": "LIST_REPOS",
        "status": "completed",
        "created_at": "2026-02-19T11:00:00",
    }

    event = _event("/v1/vendor/transactions/tx-2", "GET")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["targetVendor"] == "LH001"


@patch("vendor_registry_lambda._get_transaction_by_id_vendor")
@patch("vendor_registry_lambda._get_connection")
def test_transaction_detail_forbidden_when_vendor_not_party(
    mock_conn_ctx: MagicMock,
    mock_get: MagicMock,
) -> None:
    """Vendor cannot see transaction when they are neither source nor target."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    mock_get.return_value = None  # Guard returns None when vendor not in tx

    event = _event("/v1/vendor/transactions/tx-other", "GET")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 404
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "NOT_FOUND"
    assert "not found" in body["error"]["message"].lower()
