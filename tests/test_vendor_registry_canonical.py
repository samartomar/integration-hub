"""Unit tests for Vendor Registry Lambda - canonical operations & contracts (DB-backed, no Admin API)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from vendor_registry_lambda import handler  # noqa: E402
from vendor_registry_jwt import add_jwt_auth  # noqa: E402


def _ops_event(path: str = "/v1/vendor/canonical/operations", query: dict | None = None) -> dict:
    """Build event. path must not include query string (API Gateway separates them)."""
    return {
        "path": path,
        "rawPath": path,
        "httpMethod": "GET",
        "pathParameters": {},
        "queryStringParameters": query or {},
        "requestContext": {"http": {"method": "GET"}, "requestId": "test-req-id"},
        "headers": {},
    }


def _make_conn_mock(rows: list[dict], vendor_code: str = "LH001") -> MagicMock:
    """Build a mock connection: fetchone for vendor validation, fetchall for query rows."""
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = (vendor_code, True)
    cur.fetchall.return_value = rows
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = None
    return conn


def _op_row(
    operation_code: str = "GET_RECEIPT",
    description: str = "Get receipt",
    canonical_version: str = "v1",
    is_async_capable: bool = True,
    is_active: bool = True,
    direction_policy: str | None = "BOTH",
) -> dict:
    from uuid import uuid4

    return {
        "id": uuid4(),
        "operation_code": operation_code,
        "description": description,
        "canonical_version": canonical_version,
        "is_async_capable": is_async_capable,
        "is_active": is_active,
        "direction_policy": direction_policy,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


def _contract_row(
    operation_code: str = "GET_RECEIPT",
    canonical_version: str = "v1",
    request_schema: dict | None = None,
    response_schema: dict | None = None,
    is_active: bool = True,
) -> dict:
    from uuid import uuid4

    return {
        "id": uuid4(),
        "operation_code": operation_code,
        "canonical_version": canonical_version,
        "request_schema": request_schema or {"type": "object"},
        "response_schema": response_schema,
        "is_active": is_active,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


@patch("vendor_registry_lambda._get_connection")
def test_canonical_operations_from_db_success(mock_conn_ctx: MagicMock) -> None:
    """GET /v1/vendor/canonical/operations - DB-backed, no Admin API. Returns 200 with items."""
    rows = [_op_row("GET_RECEIPT", "Get receipt", "v1")]
    conn = _make_conn_mock(rows)
    mock_conn_ctx.return_value.__enter__.return_value = conn
    mock_conn_ctx.return_value.__exit__.return_value = None

    event = _ops_event("/v1/vendor/canonical/operations")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "transactionId" in body
    assert "correlationId" in body
    assert "items" in body
    assert len(body["items"]) == 1
    assert body["items"][0]["operationCode"] == "GET_RECEIPT"
    assert body["items"][0]["description"] == "Get receipt"
    assert body["items"][0]["canonicalVersion"] == "v1"
    assert body["items"][0]["isActive"] is True
    assert body["items"][0]["isAsyncCapable"] is True
    assert body["items"][0]["directionPolicy"] == "BOTH"
    # No Admin API call
    mock_conn_ctx.assert_called()


@patch("vendor_registry_lambda._get_connection")
def test_canonical_operations_no_admin_api_required(mock_conn_ctx: MagicMock) -> None:
    """Canonical operations works without ADMIN_API_BASE_URL (no Admin API dependency)."""
    conn = _make_conn_mock([_op_row("GET_WEATHER")])
    mock_conn_ctx.return_value.__enter__.return_value = conn
    mock_conn_ctx.return_value.__exit__.return_value = None

    with patch.dict("os.environ", {}, clear=False):
        if "ADMIN_API_BASE_URL" in __import__("os").environ:
            del __import__("os").environ["ADMIN_API_BASE_URL"]
    event = _ops_event("/v1/vendor/canonical/operations")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "items" in body
    assert body["items"][0]["operationCode"] == "GET_WEATHER"


@patch("vendor_registry_lambda._get_connection")
def test_canonical_operations_empty_result(mock_conn_ctx: MagicMock) -> None:
    """Canonical operations returns empty items when DB has none."""
    conn = _make_conn_mock([])
    mock_conn_ctx.return_value.__enter__.return_value = conn
    mock_conn_ctx.return_value.__exit__.return_value = None

    event = _ops_event("/v1/vendor/canonical/operations")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["items"] == []


@patch("vendor_registry_lambda._get_connection")
def test_canonical_contracts_from_db_success(mock_conn_ctx: MagicMock) -> None:
    """GET /v1/vendor/canonical/contracts - DB-backed, no Admin API. Returns 200 with items."""
    rows = [_contract_row("GET_RECEIPT", "v1", {"type": "object"}, None)]
    conn = _make_conn_mock(rows)
    mock_conn_ctx.return_value.__enter__.return_value = conn
    mock_conn_ctx.return_value.__exit__.return_value = None

    event = _ops_event("/v1/vendor/canonical/contracts", {"operationCode": "GET_RECEIPT"})
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "transactionId" in body
    assert "items" in body
    assert len(body["items"]) == 1
    assert body["items"][0]["operationCode"] == "GET_RECEIPT"
    assert body["items"][0]["canonicalVersion"] == "v1"
    assert body["items"][0]["requestSchema"] == {"type": "object"}
    assert body["items"][0]["isActive"] is True


@patch("vendor_registry_lambda._get_connection")
def test_canonical_contracts_no_admin_api_required(mock_conn_ctx: MagicMock) -> None:
    """Canonical contracts works without ADMIN_API_BASE_URL (no Admin API dependency)."""
    conn = _make_conn_mock([_contract_row("GET_WEATHER", "v1")])
    mock_conn_ctx.return_value.__enter__.return_value = conn
    mock_conn_ctx.return_value.__exit__.return_value = None

    event = _ops_event("/v1/vendor/canonical/contracts", {"operationCode": "GET_WEATHER"})
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "items" in body
    assert body["items"][0]["operationCode"] == "GET_WEATHER"


@patch("vendor_registry_lambda._get_connection")
def test_canonical_operations_source_target_both_required(mock_conn_ctx: MagicMock) -> None:
    """sourceVendorCode and targetVendorCode must both be provided or both omitted."""
    conn = _make_conn_mock([])
    mock_conn_ctx.return_value.__enter__.return_value = conn
    mock_conn_ctx.return_value.__exit__.return_value = None

    event = _ops_event("/v1/vendor/canonical/operations", {"sourceVendorCode": "LH001"})
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "VALIDATION_ERROR"
    assert "sourceVendorCode" in body["error"]["message"] and "targetVendorCode" in body["error"]["message"]


# --- Redrive graceful failure tests ---


def _redrive_event(transaction_id: str, method: str = "POST", auth_header: str | None = "Bearer test-token") -> dict:
    """Build redrive event. Uses JWT authorizer + x-vendor-code. auth_header for admin API call."""
    headers = {"x-vendor-code": "LH001"}
    if auth_header:
        headers["authorization"] = auth_header
    event = {
        "path": f"/v1/vendor/transactions/{transaction_id}/redrive",
        "rawPath": f"/v1/vendor/transactions/{transaction_id}/redrive",
        "httpMethod": method,
        "pathParameters": {"id": transaction_id},
        "queryStringParameters": {},
        "requestContext": {
            "http": {"method": method},
            "requestId": "test-req-id",
        },
        "headers": headers,
        "body": "{}",
    }
    add_jwt_auth(event, "LH001")
    return event


@patch("vendor_registry_lambda._get_connection")
def test_redrive_admin_api_unavailable_returns_503(mock_conn_ctx: MagicMock) -> None:
    """Redrive when ADMIN_API_BASE_URL not set returns 503 ADMIN_API_UNAVAILABLE."""
    conn = MagicMock()
    cur = MagicMock()
    tx_row = {
        "transaction_id": "tx-123",
        "source_vendor": "LH001",
        "target_vendor": "LH002",
        "status": "downstream_error",
        "request_body": {"key": "value"},
        "redrive_count": 0,
        "parent_transaction_id": None,
    }
    # First fetchone: vendor exists check; second: transaction fetch
    cur.fetchone.side_effect = [("LH001", True), tx_row]
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = None
    mock_conn_ctx.return_value.__enter__.return_value = conn
    mock_conn_ctx.return_value.__exit__.return_value = None

    with patch.dict("os.environ", {"ADMIN_API_BASE_URL": ""}, clear=False):
        event = _redrive_event("tx-123")
        resp = handler(event, None)

    assert resp["statusCode"] == 503
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "ADMIN_API_UNAVAILABLE"
    assert "Redrive is currently unavailable" in body["error"]["message"]
    assert body.get("error", {}).get("retryable") is False


@patch("vendor_registry_lambda._get_connection")
def test_redrive_missing_authorization_returns_401(mock_conn_ctx: MagicMock) -> None:
    """Redrive when Authorization header is missing returns 401 AUTH_ERROR."""
    conn = MagicMock()
    cur = MagicMock()
    tx_row = {
        "transaction_id": "tx-123",
        "source_vendor": "LH001",
        "target_vendor": "LH002",
        "status": "downstream_error",
        "request_body": {"key": "value"},
        "redrive_count": 0,
        "parent_transaction_id": None,
    }
    cur.fetchone.side_effect = [("LH001", True), tx_row]
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = None
    mock_conn_ctx.return_value.__enter__.return_value = conn
    mock_conn_ctx.return_value.__exit__.return_value = None

    with patch.dict("os.environ", {"ADMIN_API_BASE_URL": "https://admin.example.com"}, clear=False):
        event = _redrive_event("tx-123", auth_header=None)
        resp = handler(event, None)

    assert resp["statusCode"] == 401
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "AUTH_ERROR"
    assert "Authentication required" in body["error"]["message"]


# --- _fetch_admin_api still used by redrive (keep these for redrive path) ---


@patch("vendor_registry_lambda.requests.post")
def test_fetch_admin_api_post_calls_http_layer(mock_post: MagicMock) -> None:
    """_fetch_admin_api_post uses requests.post with Authorization header."""
    from vendor_registry_lambda import _fetch_admin_api_post

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"transactionId":"tx-123"}'
    mock_post.return_value = mock_resp

    status, body, err = _fetch_admin_api_post(
        "/v1/admin/redrive/tx-123",
        "https://admin.example.com",
        "Bearer eyJ.test.token",
        5.0,
        json_body={},
    )

    assert status == 200
    assert body is not None
    assert err is None
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args[1]
    assert call_kwargs["headers"]["Authorization"] == "Bearer eyJ.test.token"
    assert "admin.example.com/v1/admin/redrive" in mock_post.call_args[0][0]


def test_fetch_admin_api_missing_base_url_returns_503() -> None:
    """ADMIN_API_BASE_URL not set → 503 (used by redrive)."""
    from vendor_registry_lambda import _fetch_admin_api

    status, body, err = _fetch_admin_api(
        "/v1/registry/operations",
        {},
        "",
        "Bearer token",
        5.0,
    )

    assert status == 503
    assert body is None
    assert "ADMIN_API_BASE_URL" in (err or "")
