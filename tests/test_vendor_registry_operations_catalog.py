"""Tests for GET /v1/vendor/operations-catalog scoped by admin allowlist."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from vendor_registry_lambda import handler, _list_operations_catalog  # noqa: E402
from vendor_registry_jwt import add_jwt_auth  # noqa: E402


def _operations_catalog_event() -> dict:
    return {
        "path": "/v1/vendor/operations-catalog",
        "rawPath": "/v1/vendor/operations-catalog",
        "httpMethod": "GET",
        "pathParameters": {},
        "queryStringParameters": {},
        "requestContext": {"http": {"method": "GET"}, "requestId": "test-req-id"},
        "headers": {},
    }


@patch("vendor_registry_lambda._get_connection")
def test_operations_catalog_returns_only_admin_allowed_operations(
    mock_conn_ctx: MagicMock,
) -> None:
    """Catalog returns only operations where admin allowlist includes the vendor.
    OP_A: LH001 as source OUTBOUND. OP_B: is_any_target INBOUND. OP_C: no rule for LH001."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    def execute_side_effect(query, params=()):
        q = str(query)
        cur = mock_conn.cursor.return_value.__enter__.return_value
        if "vendors" in q and "vendor_code" in q:
            cur.fetchone.return_value = ("LH001", True)
        else:
            # Single query from _list_operations_catalog (operations JOIN allowlist)
            cur.fetchall.return_value = [
                {
                    "operation_code": "OP_A",
                    "description": "Operation A",
                    "canonical_version": "v1",
                    "is_async_capable": False,
                    "is_active": True,
                    "direction_policy": "TWO_WAY",
                },
                {
                    "operation_code": "OP_B",
                    "description": "Operation B",
                    "canonical_version": "v1",
                    "is_async_capable": False,
                    "is_active": True,
                    "direction_policy": "TWO_WAY",
                },
            ]

    mock_conn.cursor.return_value.__enter__.return_value.execute.side_effect = execute_side_effect

    event = _operations_catalog_event()
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    items = body.get("items", [])
    op_codes = [i["operationCode"] for i in items]
    assert "OP_A" in op_codes
    assert "OP_B" in op_codes
    assert "OP_C" not in op_codes
    assert len(items) == 2


@patch("vendor_registry_lambda._get_connection")
def test_operations_catalog_empty_when_no_admin_rules(
    mock_conn_ctx: MagicMock,
) -> None:
    """Vendor FOO has no admin allowlist rows; catalog returns empty items."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    def execute_side_effect(query, params=()):
        q = str(query)
        cur = mock_conn.cursor.return_value.__enter__.return_value
        if "vendors" in q and "vendor_code" in q:
            cur.fetchone.return_value = ("FOO", True)
        else:
            # JOIN returns no rows when no allowlist matches
            cur.fetchall.return_value = []

    mock_conn.cursor.return_value.__enter__.return_value.execute.side_effect = execute_side_effect

    event = _operations_catalog_event()
    add_jwt_auth(event, "FOO")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body.get("items") == []


def test_list_operations_catalog_empty_when_vendor_code_missing() -> None:
    """_list_operations_catalog returns [] when vendor_code is missing (safety fallback)."""
    mock_conn = MagicMock()
    result = _list_operations_catalog(mock_conn, vendor_code=None)
    assert result == []

    result = _list_operations_catalog(mock_conn, vendor_code="")
    assert result == []

    result = _list_operations_catalog(mock_conn, vendor_code="   ")
    assert result == []
