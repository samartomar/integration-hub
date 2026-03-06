"""Performance & safety tests for transaction endpoints.

Ensures transaction-list endpoints:
- Enforce maximum limit (clamped server-side)
- Always apply time window (from/to required)
- Do not allow unbounded scans
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from audit_lambda import handler as audit_handler  # noqa: E402
from vendor_registry_lambda import handler as vendor_handler  # noqa: E402
from vendor_registry_jwt import add_jwt_auth  # noqa: E402

AUDIT_HEADERS = {"Authorization": "Bearer test-admin-jwt"}


# --- Admin Audit Lambda: GET /v1/audit/transactions ---


@patch("audit_lambda._get_connection")
@patch("audit_lambda._query_transactions")
def test_audit_transactions_list_requires_from_to(mock_query: MagicMock, mock_conn: MagicMock) -> None:
    """GET /v1/audit/transactions returns 400 when from or to is missing."""
    mock_conn.return_value.__enter__.return_value = MagicMock()

    event = {
        "path": "/v1/audit/transactions",
        "rawPath": "/v1/audit/transactions",
        "httpMethod": "GET",
        "headers": AUDIT_HEADERS,
        "queryStringParameters": {"vendorCode": "LH001"},  # no from/to
        "pathParameters": {},
        "requestContext": {"http": {"method": "GET"}},
    }

    resp = audit_handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "from and to" in body["error"]["message"].lower()
    mock_query.assert_not_called()


@patch("audit_lambda._get_connection")
@patch("audit_lambda._query_transactions")
def test_audit_transactions_list_enforces_max_limit(mock_query: MagicMock, mock_conn: MagicMock) -> None:
    """Audit transactions list clamps limit to MAX_LIMIT (200)."""
    mock_conn.return_value.__enter__.return_value = MagicMock()
    mock_query.return_value = ([], None)

    event = {
        "path": "/v1/audit/transactions",
        "rawPath": "/v1/audit/transactions",
        "httpMethod": "GET",
        "headers": AUDIT_HEADERS,
        "queryStringParameters": {
            "from": "2026-01-01T00:00:00Z",
            "to": "2026-01-02T00:00:00Z",
            "limit": "999",
        },
        "pathParameters": {},
        "requestContext": {"http": {"method": "GET"}},
    }

    resp = audit_handler(event, None)

    assert resp["statusCode"] == 200
    call_kwargs = mock_query.call_args[1]
    assert call_kwargs["limit"] == 200


# --- Vendor Registry: GET /v1/vendor/transactions ---


@patch("vendor_registry_lambda._query_vendor_transactions")
@patch("vendor_registry_lambda._get_connection")
def test_vendor_transactions_list_requires_from_to(
    mock_conn: MagicMock,
    mock_query: MagicMock,
) -> None:
    """GET /v1/vendor/transactions returns 400 when from or to is missing."""
    mock_conn_obj = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn_obj.cursor.return_value = cursor
    mock_conn.return_value.__enter__.return_value = mock_conn_obj

    event = {
        "path": "/v1/vendor/transactions",
        "rawPath": "/v1/vendor/transactions",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {"direction": "all"},  # no from/to
        "pathParameters": {},
        "requestContext": {"http": {"method": "GET"}},
    }
    add_jwt_auth(event, "LH001")

    resp = vendor_handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "from and to" in body["error"]["message"].lower()
    mock_query.assert_not_called()


@patch("vendor_registry_lambda._query_vendor_transactions")
@patch("vendor_registry_lambda._get_connection")
def test_vendor_transactions_list_enforces_max_limit(
    mock_conn: MagicMock,
    mock_query: MagicMock,
) -> None:
    """Vendor transactions list clamps limit to TX_MAX_LIMIT (200)."""
    mock_conn_obj = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn_obj.cursor.return_value = cursor
    mock_conn.return_value.__enter__.return_value = mock_conn_obj

    mock_query.return_value = ([], None)

    event = {
        "path": "/v1/vendor/transactions",
        "rawPath": "/v1/vendor/transactions",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {
            "from": "2026-01-01T00:00:00Z",
            "to": "2026-01-02T00:00:00Z",
            "limit": "500",
        },
        "pathParameters": {},
        "requestContext": {"http": {"method": "GET"}},
    }
    add_jwt_auth(event, "LH001")

    resp = vendor_handler(event, None)

    assert resp["statusCode"] == 200
    # _query_vendor_transactions(conn, vendor_code, direction, from_ts, to_ts, operation, status, search, limit, cursor)
    # limit is the 9th positional arg (index 8)
    args = mock_query.call_args[0]
    assert len(args) >= 9, "_query_vendor_transactions expected at least 9 args"
    assert args[8] == 200, f"Expected limit=200 (clamped from 500), got {args[8]!r}"
