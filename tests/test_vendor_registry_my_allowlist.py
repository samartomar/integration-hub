"""Unit tests for Vendor Registry Lambda - GET /v1/vendor/my-allowlist."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from vendor_registry_lambda import handler  # noqa: E402
from vendor_registry_jwt import add_jwt_auth  # noqa: E402


def _my_allowlist_event() -> dict:
    return {
        "path": "/v1/vendor/my-allowlist",
        "rawPath": "/v1/vendor/my-allowlist",
        "httpMethod": "GET",
        "pathParameters": {},
        "queryStringParameters": {},
        "requestContext": {"http": {"method": "GET"}, "requestId": "test-req-id"},
        "headers": {},
    }


def _mock_cursor_with_rows(rows: list[dict], fetchone: tuple[str, bool] | None = None) -> MagicMock:
    """Create a mock cursor that returns rows from fetchall()."""
    cursor = MagicMock()
    cursor.execute = MagicMock()
    cursor.fetchall.return_value = rows
    if fetchone is not None:
        cursor.fetchone.return_value = fetchone
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    return cursor


@patch("vendor_registry_lambda._get_connection")
def test_my_allowlist_success_outbound_inbound_partition(
    mock_conn_ctx: MagicMock,
) -> None:
    """Direct DB returns allowlist rows; correct outbound/inbound partition for vendor LH001."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    outbound_rows = [
        {"id": "a1", "source_vendor_code": "LH001", "target_vendor_code": "LH002", "operation_code": "GET_RECEIPT", "flow_direction": "BOTH", "created_at": "2024-01-01T00:00:00"},
        {"id": "a3", "source_vendor_code": "LH001", "target_vendor_code": "STRIPE", "operation_code": "GET_RECEIPT", "flow_direction": "BOTH", "created_at": "2024-01-03T00:00:00"},
    ]
    inbound_rows = [
        {"id": "a2", "source_vendor_code": "GITHUB", "target_vendor_code": "LH001", "operation_code": "LIST_REPOS", "flow_direction": "BOTH", "created_at": "2024-01-02T00:00:00"},
    ]
    admin_rows: list[dict] = []
    vendor_rules_rows = [
        {"operation_code": "GET_RECEIPT", "flow_direction": "BOTH", "source_vendor_code": "LH001", "target_vendor_code": "LH002"},
        {"operation_code": "GET_RECEIPT", "flow_direction": "BOTH", "source_vendor_code": "LH001", "target_vendor_code": "STRIPE"},
        {"operation_code": "LIST_REPOS", "flow_direction": "BOTH", "source_vendor_code": "GITHUB", "target_vendor_code": "LH001"},
    ]
    supported_rows = [
        {"operation_code": "GET_RECEIPT", "supports_outbound": True, "supports_inbound": False},
        {"operation_code": "LIST_REPOS", "supports_outbound": False, "supports_inbound": True},
    ]
    cursor_vendor_check = _mock_cursor_with_rows([], ("LH001", True))
    cursor_out = _mock_cursor_with_rows(outbound_rows)
    cursor_in = _mock_cursor_with_rows(inbound_rows)
    cursor_admin = _mock_cursor_with_rows(admin_rows)
    cursor_vendor = _mock_cursor_with_rows(vendor_rules_rows)
    cursor_supported = _mock_cursor_with_rows(supported_rows)
    cursor_eligible = _mock_cursor_with_rows([])
    mock_conn.cursor.return_value.__enter__.side_effect = [
        cursor_vendor_check, cursor_out, cursor_in, cursor_admin, cursor_vendor, cursor_supported, cursor_eligible,
    ]
    mock_conn.cursor.return_value.__exit__.return_value = False

    event = _my_allowlist_event()
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "transactionId" in body
    assert "correlationId" in body
    assert "outbound" in body
    assert "inbound" in body
    outbound = body["outbound"]
    inbound = body["inbound"]
    assert len(outbound) == 2
    assert len(inbound) == 1
    assert outbound[0]["sourceVendor"] == "LH001" and outbound[0]["targetVendor"] == "LH002"
    assert outbound[1]["sourceVendor"] == "LH001" and outbound[1]["targetVendor"] == "STRIPE"
    assert inbound[0]["sourceVendor"] == "GITHUB" and inbound[0]["targetVendor"] == "LH001"


@patch("vendor_registry_lambda._get_connection")
def test_my_allowlist_outbound_vendor_owned_only(
    mock_conn_ctx: MagicMock,
) -> None:
    """Vendor-owned outbound rules only. Hub wildcard (source='*') is eligibility, not in my-allowlist.
    Outbound query filters source=me, so source='*' rows are never returned."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    outbound_rows: list[dict] = []
    inbound_rows: list[dict] = []
    supported_rows = [{"operation_code": "GET_WEATHER", "supports_outbound": True, "supports_inbound": True}]

    cursor_vendor_check = _mock_cursor_with_rows([], ("LH001", True))
    cursor_out = _mock_cursor_with_rows(outbound_rows)
    cursor_in = _mock_cursor_with_rows(inbound_rows)
    cursor_admin = _mock_cursor_with_rows([])
    cursor_vendor = _mock_cursor_with_rows([])
    cursor_supported = _mock_cursor_with_rows(supported_rows)
    cursor_eligible = _mock_cursor_with_rows([])
    mock_conn.cursor.return_value.__enter__.side_effect = [
        cursor_vendor_check, cursor_out, cursor_in, cursor_admin, cursor_vendor, cursor_supported, cursor_eligible,
    ]
    mock_conn.cursor.return_value.__exit__.return_value = False

    event = _my_allowlist_event()
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    outbound = body["outbound"]
    inbound = body["inbound"]
    assert len(outbound) == 0
    assert len(inbound) == 0


@patch("vendor_registry_lambda._get_connection")
def test_my_allowlist_inbound_wildcard_visible(
    mock_conn_ctx: MagicMock,
) -> None:
    """Inbound: target=me returns rows. Vendor LH002 created rule (source=*, target=LH002) via Access control."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    outbound_rows: list[dict] = []
    inbound_rows = [
        {
            "id": "w1",
            "source_vendor_code": "*",
            "target_vendor_code": "LH002",
            "operation_code": "GET_RECEIPT_v1",
            "flow_direction": "BOTH",
            "created_at": "2024-01-01T00:00:00",
        },
    ]
    vendor_rules_rows = [
        {"operation_code": "GET_RECEIPT_v1", "flow_direction": "BOTH", "source_vendor_code": "*", "target_vendor_code": "LH002"},
    ]
    supported_rows = [{"operation_code": "GET_RECEIPT_v1", "supports_outbound": False, "supports_inbound": True}]

    cursor_vendor_check = _mock_cursor_with_rows([], ("LH002", True))
    cursor_out = _mock_cursor_with_rows(outbound_rows)
    cursor_in = _mock_cursor_with_rows(inbound_rows)
    cursor_admin = _mock_cursor_with_rows([])
    cursor_vendor = _mock_cursor_with_rows(vendor_rules_rows)
    cursor_supported = _mock_cursor_with_rows(supported_rows)
    cursor_eligible = _mock_cursor_with_rows([])
    mock_conn.cursor.return_value.__enter__.side_effect = [
        cursor_vendor_check, cursor_out, cursor_in, cursor_admin, cursor_vendor, cursor_supported, cursor_eligible,
    ]
    mock_conn.cursor.return_value.__exit__.return_value = False

    event = _my_allowlist_event()
    add_jwt_auth(event, "LH002")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    outbound = body["outbound"]
    inbound = body["inbound"]
    assert len(outbound) == 0
    assert len(inbound) == 1
    assert inbound[0]["sourceVendor"] == "*"
    assert inbound[0]["targetVendor"] == "LH002"
    assert inbound[0]["operation"] == "GET_RECEIPT_v1"


@patch("vendor_registry_lambda._get_connection")
def test_my_allowlist_empty_lists(
    mock_conn_ctx: MagicMock,
) -> None:
    """DB returns no rows; outbound and inbound are empty lists."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor_vendor_check = _mock_cursor_with_rows([], ("LH001", True))
    cursor_empty = _mock_cursor_with_rows([])
    supported_empty = _mock_cursor_with_rows([{"operation_code": "OP1", "supports_outbound": True, "supports_inbound": True}])
    mock_conn.cursor.return_value.__enter__.side_effect = [
        cursor_vendor_check, cursor_empty, cursor_empty, cursor_empty, cursor_empty, supported_empty, cursor_empty,
    ]
    mock_conn.cursor.return_value.__exit__.return_value = False

    event = _my_allowlist_event()
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["outbound"] == []
    assert body["inbound"] == []


@patch("vendor_registry_lambda._get_connection")
def test_my_allowlist_db_error_maps_to_internal_error(
    mock_conn_ctx: MagicMock,
) -> None:
    """DB exception → 500 INTERNAL_ERROR."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = MagicMock()
    mock_cursor.__enter__.return_value = mock_cursor
    mock_cursor.__exit__.return_value = False
    mock_cursor.execute.side_effect = Exception("Connection refused")
    mock_cursor.fetchone.return_value = ("LH001", True)
    mock_conn.cursor.return_value = mock_cursor

    event = _my_allowlist_event()
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 500
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "INTERNAL_ERROR"


def test_my_allowlist_no_vendor_code_returns_401() -> None:
    """When vendor code cannot be resolved: 401 AUTH_ERROR."""
    event = _my_allowlist_event()
    add_jwt_auth(event, "")

    with patch("vendor_registry_lambda._get_connection"):
        resp = handler(event, None)

    assert resp["statusCode"] == 401
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "AUTH_ERROR"
