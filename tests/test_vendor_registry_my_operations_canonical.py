"""Tests for canonical pass-through in vendor my-operations."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from vendor_registry_lambda import handler  # noqa: E402
from vendor_registry_jwt import add_jwt_auth  # noqa: E402


def _my_operations_event() -> dict:
    return {
        "path": "/v1/vendor/my-operations",
        "rawPath": "/v1/vendor/my-operations",
        "httpMethod": "GET",
        "pathParameters": {},
        "queryStringParameters": {},
        "requestContext": {"http": {"method": "GET"}, "requestId": "test-req-id"},
        "headers": {},
    }


@patch("vendor_registry_lambda._get_connection")
def test_my_operations_outbound_get_canonical_pass_through(mock_conn_ctx: MagicMock) -> None:
    """Outbound GET, canonical only: mappingConfigured True, usesCanonical* True, status ready."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    def execute_side_effect(query, params=()):
        q = str(query) if hasattr(query, "decode") else str(query)
        cur = mock_conn.cursor.return_value.__enter__.return_value
        if "vendors" in q and "vendor_code" in q:
            cur.fetchone.return_value = ("LH001", True)
        elif "vendor_operation_allowlist" in q:
            cur.fetchall.return_value = [
                {
                    "source_vendor_code": "LH001",
                    "target_vendor_code": "LH002",
                    "is_any_source": False,
                    "is_any_target": False,
                    "operation_code": "GET_WEATHER",
                    "flow_direction": "OUTBOUND",
                },
            ]
        elif "operations" in q and "operation_contracts" not in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_WEATHER", "canonical_version": "v1", "direction_policy": "TWO_WAY", "is_active": True},
            ]
        elif "operation_contracts" in q and "vendor_operation_contracts" not in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_WEATHER", "canonical_version": "v1", "request_schema": {"type": "object"}, "response_schema": {"type": "object"}},
            ]
        elif "vendor_operation_contracts" in q:
            cur.fetchall.return_value = []  # No vendor override - canonical pass-through
        elif "vendor_operation_mappings" in q:
            cur.fetchall.return_value = []  # No mappings
        elif "vendor_endpoints" in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_WEATHER", "verification_status": "VERIFIED"},
            ]
        else:
            cur.fetchall.return_value = []

    mock_conn.cursor.return_value.__enter__.return_value.execute.side_effect = execute_side_effect

    event = _my_operations_event()
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    outbound = body.get("outbound", [])
    assert len(outbound) == 1
    row = outbound[0]
    assert row["operationCode"] == "GET_WEATHER"
    assert row["direction"] == "outbound"
    assert row["mappingConfigured"] is True
    assert row["effectiveMappingConfigured"] is True
    assert row["usesCanonicalRequestMapping"] is True
    assert row["usesCanonicalResponseMapping"] is True
    assert row["hasVendorRequestMapping"] is False
    assert row["hasVendorResponseMapping"] is False
    assert row["status"] == "ready"
    assert row.get("contractStatus") == "OK", "Canonical-only ops should have contract OK"
    assert "MISSING_VENDOR_CONTRACT" not in row.get("issues", [])
    assert "MISSING_REQUEST_MAPPING" not in row.get("issues", [])
    assert "MISSING_RESPONSE_MAPPING" not in row.get("issues", [])


@patch("vendor_registry_lambda._get_connection")
def test_my_operations_outbound_post_canonical_pass_through(mock_conn_ctx: MagicMock) -> None:
    """Outbound POST, canonical only: same expectations."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    def execute_side_effect(query, params=()):
        q = str(query) if hasattr(query, "decode") else str(query)
        cur = mock_conn.cursor.return_value.__enter__.return_value
        if "vendors" in q and "vendor_code" in q:
            cur.fetchone.return_value = ("LH001", True)
        elif "vendor_operation_allowlist" in q:
            cur.fetchall.return_value = [
                {
                    "source_vendor_code": "LH001",
                    "target_vendor_code": "LH002",
                    "is_any_source": False,
                    "is_any_target": False,
                    "operation_code": "SEND_WEATHER",
                    "flow_direction": "OUTBOUND",
                },
            ]
        elif "operations" in q and "operation_contracts" not in q:
            cur.fetchall.return_value = [
                {"operation_code": "SEND_WEATHER", "canonical_version": "v1", "direction_policy": "TWO_WAY", "is_active": True},
            ]
        elif "operation_contracts" in q and "vendor_operation_contracts" not in q:
            cur.fetchall.return_value = [
                {"operation_code": "SEND_WEATHER", "canonical_version": "v1", "request_schema": {"type": "object", "properties": {"body": {}}}, "response_schema": {"type": "object"}},
            ]
        elif "vendor_operation_contracts" in q:
            cur.fetchall.return_value = []
        elif "vendor_operation_mappings" in q:
            cur.fetchall.return_value = []
        elif "vendor_endpoints" in q:
            cur.fetchall.return_value = [
                {"operation_code": "SEND_WEATHER", "verification_status": "VERIFIED"},
            ]
        else:
            cur.fetchall.return_value = []

    mock_conn.cursor.return_value.__enter__.return_value.execute.side_effect = execute_side_effect

    event = _my_operations_event()
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    outbound = body.get("outbound", [])
    assert len(outbound) == 1
    row = outbound[0]
    assert row["operationCode"] == "SEND_WEATHER"
    assert row["mappingConfigured"] is True
    assert row["effectiveMappingConfigured"] is True
    assert row["usesCanonicalRequestMapping"] is True
    assert row["usesCanonicalResponseMapping"] is True
    assert row["status"] == "ready"


@patch("vendor_registry_lambda._get_connection")
def test_my_operations_vendor_override_without_mapping_not_configured(mock_conn_ctx: MagicMock) -> None:
    """Vendor override contract without mapping → mappingConfigured False, status needs_setup."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    def execute_side_effect(query, params=()):
        q = str(query) if hasattr(query, "decode") else str(query)
        cur = mock_conn.cursor.return_value.__enter__.return_value
        if "vendors" in q and "vendor_code" in q:
            cur.fetchone.return_value = ("LH001", True)
        elif "vendor_operation_allowlist" in q:
            cur.fetchall.return_value = [
                {
                    "source_vendor_code": "LH001",
                    "target_vendor_code": "LH002",
                    "is_any_source": False,
                    "is_any_target": False,
                    "operation_code": "GET_WEATHER",
                    "flow_direction": "OUTBOUND",
                },
            ]
        elif "operations" in q and "operation_contracts" not in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_WEATHER", "canonical_version": "v1", "direction_policy": "TWO_WAY", "is_active": True},
            ]
        elif "operation_contracts" in q and "vendor_operation_contracts" not in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_WEATHER", "canonical_version": "v1", "request_schema": {"type": "object"}, "response_schema": {"type": "object"}},
            ]
        elif "vendor_operation_contracts" in q and "ANY" not in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_WEATHER", "canonical_version": "v1", "is_active": True, "request_schema": {"type": "object", "properties": {"custom": {}}}, "response_schema": {"type": "object"}},
            ]
        elif "vendor_operation_contracts" in q and "ANY" in q:
            cur.fetchall.return_value = []
        elif "vendor_operation_mappings" in q:
            cur.fetchall.return_value = []
        elif "vendor_endpoints" in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_WEATHER", "verification_status": "VERIFIED"},
            ]
        else:
            cur.fetchall.return_value = []

    mock_conn.cursor.return_value.__enter__.return_value.execute.side_effect = execute_side_effect

    event = _my_operations_event()
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    outbound = body.get("outbound", [])
    assert len(outbound) == 1
    row = outbound[0]
    assert row["operationCode"] == "GET_WEATHER"
    assert row["mappingConfigured"] is False
    assert row.get("effectiveMappingConfigured") is False
    assert row["usesCanonicalRequestMapping"] is False
    assert row["usesCanonicalResponseMapping"] is False
    assert row["status"] == "needs_setup"
