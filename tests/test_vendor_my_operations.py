"""Unit tests for Vendor Registry Lambda - GET /v1/vendor/my-operations."""

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
def test_my_operations_ready_outbound(
    mock_conn_ctx: MagicMock,
) -> None:
    """Outbound flow fully configured → status ready, no issues.
    Uses FROM_CANONICAL + TO_CANONICAL_RESPONSE (provider flow / Flow Builder baseline)."""
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
                    "operation_code": "GET_RECEIPT",
                    "flow_direction": "OUTBOUND",
                },
            ]
        elif "operations" in q and "operation_contracts" not in q:
            cur.fetchall.return_value = [{"operation_code": "GET_RECEIPT", "canonical_version": "v1"}]
        elif "operation_contracts" in q and "vendor_operation_contracts" not in q:
            cur.fetchall.return_value = [{"operation_code": "GET_RECEIPT", "canonical_version": "v1"}]
        elif "vendor_operation_contracts" in q and "ANY" in q:
            cur.fetchall.return_value = []
        elif "vendor_operation_contracts" in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "is_active": True, "request_schema": {"type": "object"}, "response_schema": {"type": "object"}},
            ]
        elif "vendor_operation_mappings" in q:
            cur.fetchall.return_value = [
                {"vendor_code": "LH001", "operation_code": "GET_RECEIPT", "canonical_version": "v1", "direction": "FROM_CANONICAL", "flow_direction": "OUTBOUND"},
                {"vendor_code": "LH001", "operation_code": "GET_RECEIPT", "canonical_version": "v1", "direction": "TO_CANONICAL_RESPONSE", "flow_direction": "OUTBOUND"},
            ]
        elif "vendor_endpoints" in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_RECEIPT", "verification_status": "VERIFIED"},
            ]
        elif "request_schema" in q and "operation_contracts" in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": {"type": "object"}, "response_schema": {"type": "object"}},
            ]
        else:
            cur.fetchall.return_value = []

    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = execute_side_effect
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    event = _my_operations_event()
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "outbound" in body
    assert "inbound" in body
    outbound = body["outbound"]
    assert len(outbound) == 1
    row = outbound[0]
    assert row["operationCode"] == "GET_RECEIPT"
    assert row["partnerVendorCode"] == "LH002"
    assert row["direction"] == "outbound"
    assert row["status"] == "ready"
    assert row["issues"] == []
    assert row["contractStatus"] == "OK"
    assert row["mappingStatus"] == "OK"
    assert row["endpointStatus"] == "OK"
    assert row["allowlistStatus"] == "OK"


@patch("vendor_registry_lambda._get_connection")
def test_my_operations_lh001_get_weather_identity_mappings(
    mock_conn_ctx: MagicMock,
) -> None:
    """LH001 GET_WEATHER with identity mappings (FROM_CANONICAL + TO_CANONICAL_RESPONSE, flow_direction OUTBOUND):
    vendor_endpoints (OUTBOUND), allowlist admin rule, two mapping rows with empty {}, no vendor_operation_contracts.
    mappingConfigured and mappingStatus must be OK; overall readiness only fails if something else missing."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    def execute_side_effect(query, params=()):
        q = str(query) if hasattr(query, "decode") else str(query)
        cur = mock_conn.cursor.return_value.__enter__.return_value
        if "vendors" in q and "vendor_code" in q:
            cur.fetchone.return_value = ("LH001", True)
        elif "vendor_operation_allowlist" in q:
            cur.fetchall.return_value = [
                {"source_vendor_code": "LH001", "target_vendor_code": "LH002", "operation_code": "GET_WEATHER", "flow_direction": "OUTBOUND"},
            ]
        elif "operations" in q and "operation_contracts" not in q:
            cur.fetchall.return_value = [{"operation_code": "GET_WEATHER", "canonical_version": "v1"}]
        elif "operation_contracts" in q and "vendor_operation_contracts" not in q:
            cur.fetchall.return_value = [{"operation_code": "GET_WEATHER", "canonical_version": "v1"}]
        elif "vendor_operation_contracts" in q:
            cur.fetchall.return_value = []
        elif "vendor_operation_mappings" in q:
            cur.fetchall.return_value = [
                {"vendor_code": "LH001", "operation_code": "GET_WEATHER", "canonical_version": "v1", "direction": "FROM_CANONICAL", "flow_direction": "OUTBOUND"},
                {"vendor_code": "LH001", "operation_code": "GET_WEATHER", "canonical_version": "v1", "direction": "TO_CANONICAL_RESPONSE", "flow_direction": "OUTBOUND"},
            ]
        elif "vendor_endpoints" in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_WEATHER", "verification_status": "VERIFIED"},
            ]
        elif "request_schema" in q and "operation_contracts" in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_WEATHER", "canonical_version": "v1", "request_schema": {"type": "object"}, "response_schema": {"type": "object"}},
            ]
        else:
            cur.fetchall.return_value = []

    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = execute_side_effect
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    event = _my_operations_event()
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    outbound = body["outbound"]
    assert len(outbound) == 1
    row = outbound[0]
    assert row["operationCode"] == "GET_WEATHER"
    assert row["mappingConfigured"] is True
    assert row["mappingStatus"] == "OK"
    assert "MISSING_REQUEST_MAPPING" not in row.get("issues", [])
    assert "MISSING_RESPONSE_MAPPING" not in row.get("issues", [])


@patch("vendor_registry_lambda._get_connection")
def test_my_operations_missing_mapping(
    mock_conn_ctx: MagicMock,
) -> None:
    """Outbound flow missing request mapping → issues contains MISSING_REQUEST_MAPPING, status needs_setup."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    def execute_side_effect(query, params=()):
        q = str(query) if hasattr(query, "decode") else str(query)
        cur = mock_conn.cursor.return_value.__enter__.return_value
        if "vendors" in q and "vendor_code" in q:
            cur.fetchone.return_value = ("LH001", True)
        elif "vendor_operation_allowlist" in q:
            cur.fetchall.return_value = [
                {"source_vendor_code": "LH001", "target_vendor_code": "LH002", "operation_code": "GET_RECEIPT", "flow_direction": "OUTBOUND"},
            ]
        elif "operations" in q and "operation_contracts" not in q:
            cur.fetchall.return_value = [{"operation_code": "GET_RECEIPT", "canonical_version": "v1"}]
        elif "operation_contracts" in q and "vendor_operation_contracts" not in q:
            cur.fetchall.return_value = [{"operation_code": "GET_RECEIPT", "canonical_version": "v1"}]
        elif "vendor_operation_contracts" in q and "request_schema" in q:
            cur.fetchall.return_value = [
                {"vendor_code": "LH001", "operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": {"type": "object", "vendorFormat": True}, "response_schema": {"type": "object"}},
            ]
        elif "vendor_operation_contracts" in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "is_active": True},
            ]
        elif "vendor_operation_mappings" in q:
            cur.fetchall.return_value = [
                {"vendor_code": "LH001", "operation_code": "GET_RECEIPT", "canonical_version": "v1", "direction": "FROM_CANONICAL_RESPONSE", "flow_direction": "OUTBOUND"},
            ]
        elif "vendor_endpoints" in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_RECEIPT", "verification_status": "VERIFIED"},
            ]
        elif "request_schema" in q and "operation_contracts" in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": {"type": "object"}, "response_schema": {"type": "object"}},
            ]
        else:
            cur.fetchall.return_value = []

    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = execute_side_effect
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    event = _my_operations_event()
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    outbound = body["outbound"]
    assert len(outbound) == 1
    row = outbound[0]
    assert row["status"] == "needs_setup"
    assert "MISSING_REQUEST_MAPPING" in row["issues"]
    assert row["requestMappingStatus"] == "error_required_missing"


@patch("vendor_registry_lambda._get_connection")
def test_my_operations_inbound_wildcard_partner(
    mock_conn_ctx: MagicMock,
) -> None:
    """Inbound rule with wildcard partner (*) - verify partnerVendorCode is '*'."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    def execute_side_effect(query, params=()):
        q = str(query) if hasattr(query, "decode") else str(query)
        cur = mock_conn.cursor.return_value.__enter__.return_value
        if "vendors" in q and "vendor_code" in q:
            cur.fetchone.return_value = ("LH001", True)
        elif "vendor_operation_allowlist" in q:
            cur.fetchall.return_value = [
                {"source_vendor_code": "*", "target_vendor_code": "LH001", "operation_code": "GET_RECEIPT", "flow_direction": "INBOUND"},
            ]
        elif "operations" in q and "operation_contracts" not in q:
            cur.fetchall.return_value = [{"operation_code": "GET_RECEIPT", "canonical_version": "v1"}]
        elif "operation_contracts" in q and "vendor_operation_contracts" not in q:
            cur.fetchall.return_value = [{"operation_code": "GET_RECEIPT", "canonical_version": "v1"}]
        elif "vendor_operation_contracts" in q and "ANY" in q:
            cur.fetchall.return_value = []
        elif "vendor_operation_contracts" in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "is_active": True, "request_schema": {"type": "object"}, "response_schema": {"type": "object"}},
            ]
        elif "vendor_operation_mappings" in q:
            cur.fetchall.return_value = [
                {"vendor_code": "LH001", "operation_code": "GET_RECEIPT", "canonical_version": "v1", "direction": "TO_CANONICAL", "flow_direction": "INBOUND"},
                {"vendor_code": "LH001", "operation_code": "GET_RECEIPT", "canonical_version": "v1", "direction": "FROM_CANONICAL_RESPONSE", "flow_direction": "INBOUND"},
            ]
        elif "vendor_endpoints" in q:
            cur.fetchall.return_value = []
        elif "request_schema" in q and "operation_contracts" in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": {"type": "object"}, "response_schema": {"type": "object"}},
            ]
        else:
            cur.fetchall.return_value = []

    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = execute_side_effect
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    event = _my_operations_event()
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    inbound = body["inbound"]
    assert len(inbound) == 1
    row = inbound[0]
    assert row["direction"] == "inbound"
    assert row["partnerVendorCode"] == "*"


@patch("vendor_registry_lambda._get_connection")
def test_my_operations_vendor_scoping(
    mock_conn_ctx: MagicMock,
) -> None:
    """Calling as LH001 must not see flows for LH002 - vendor_code comes from JWT."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = ("LH001", True)
    mock_cursor.fetchall.return_value = []
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    event = _my_operations_event()
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["outbound"] == []
    assert body["inbound"] == []


@patch("vendor_registry_lambda._get_connection")
def test_my_operations_inactive_contract_needs_attention(
    mock_conn_ctx: MagicMock,
) -> None:
    """Outbound with inactive contract → contractStatus INACTIVE, status needs_attention."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    def execute_side_effect(query, params=()):
        q = str(query) if hasattr(query, "decode") else str(query)
        cur = mock_conn.cursor.return_value.__enter__.return_value
        if "vendors" in q and "vendor_code" in q:
            cur.fetchone.return_value = ("LH001", True)
        elif "vendor_operation_allowlist" in q:
            cur.fetchall.return_value = [
                {"source_vendor_code": "LH001", "target_vendor_code": "LH002", "operation_code": "GET_RECEIPT", "flow_direction": "OUTBOUND"},
            ]
        elif "operations" in q and "operation_contracts" not in q:
            cur.fetchall.return_value = [{"operation_code": "GET_RECEIPT", "canonical_version": "v1"}]
        elif "operation_contracts" in q and "vendor_operation_contracts" not in q:
            cur.fetchall.return_value = [{"operation_code": "GET_RECEIPT", "canonical_version": "v1"}]
        elif "vendor_operation_contracts" in q and "ANY" in q:
            cur.fetchall.return_value = []
        elif "vendor_operation_contracts" in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "is_active": False, "request_schema": {"type": "object"}, "response_schema": {"type": "object"}},
            ]
        elif "vendor_operation_mappings" in q:
            cur.fetchall.return_value = [
                {"vendor_code": "LH001", "operation_code": "GET_RECEIPT", "canonical_version": "v1", "direction": "FROM_CANONICAL", "flow_direction": "OUTBOUND"},
                {"vendor_code": "LH001", "operation_code": "GET_RECEIPT", "canonical_version": "v1", "direction": "TO_CANONICAL_RESPONSE", "flow_direction": "OUTBOUND"},
            ]
        elif "vendor_endpoints" in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_RECEIPT", "verification_status": "VERIFIED"},
            ]
        elif "request_schema" in q and "operation_contracts" in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": {"type": "object"}, "response_schema": {"type": "object"}},
            ]
        else:
            cur.fetchall.return_value = []

    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = execute_side_effect
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    event = _my_operations_event()
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    outbound = body["outbound"]
    assert len(outbound) == 1
    row = outbound[0]
    assert row["contractStatus"] == "INACTIVE"
    assert row["status"] == "needs_attention"


@patch("vendor_registry_lambda._get_connection")
def test_my_operations_unverified_endpoint_needs_attention(
    mock_conn_ctx: MagicMock,
) -> None:
    """Outbound with unverified endpoint → endpointStatus UNVERIFIED, status needs_attention."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    def execute_side_effect(query, params=()):
        q = str(query) if hasattr(query, "decode") else str(query)
        cur = mock_conn.cursor.return_value.__enter__.return_value
        if "vendors" in q and "vendor_code" in q:
            cur.fetchone.return_value = ("LH001", True)
        elif "vendor_operation_allowlist" in q:
            cur.fetchall.return_value = [
                {"source_vendor_code": "LH001", "target_vendor_code": "LH002", "operation_code": "GET_RECEIPT", "flow_direction": "OUTBOUND"},
            ]
        elif "operations" in q and "operation_contracts" not in q:
            cur.fetchall.return_value = [{"operation_code": "GET_RECEIPT", "canonical_version": "v1"}]
        elif "operation_contracts" in q and "vendor_operation_contracts" not in q:
            cur.fetchall.return_value = [{"operation_code": "GET_RECEIPT", "canonical_version": "v1"}]
        elif "vendor_operation_contracts" in q and "ANY" in q:
            cur.fetchall.return_value = []
        elif "vendor_operation_contracts" in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "is_active": True, "request_schema": {"type": "object"}, "response_schema": {"type": "object"}},
            ]
        elif "vendor_operation_mappings" in q:
            cur.fetchall.return_value = [
                {"vendor_code": "LH001", "operation_code": "GET_RECEIPT", "canonical_version": "v1", "direction": "FROM_CANONICAL", "flow_direction": "OUTBOUND"},
                {"vendor_code": "LH001", "operation_code": "GET_RECEIPT", "canonical_version": "v1", "direction": "TO_CANONICAL_RESPONSE", "flow_direction": "OUTBOUND"},
            ]
        elif "vendor_endpoints" in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_RECEIPT", "verification_status": "PENDING"},
            ]
        elif "request_schema" in q and "operation_contracts" in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": {"type": "object"}, "response_schema": {"type": "object"}},
            ]
        else:
            cur.fetchall.return_value = []

    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = execute_side_effect
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    event = _my_operations_event()
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    outbound = body["outbound"]
    assert len(outbound) == 1
    row = outbound[0]
    assert row["endpointStatus"] == "UNVERIFIED"
    assert row["status"] == "needs_attention"


@patch("vendor_registry_lambda._get_connection")
def test_my_operations_optional_mapping_missing_still_ready(
    mock_conn_ctx: MagicMock,
) -> None:
    """Optional mapping missing (vendor conforms to canonical) → status ready, warning_optional_missing."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    def execute_side_effect(query, params=()):
        q = str(query) if hasattr(query, "decode") else str(query)
        cur = mock_conn.cursor.return_value.__enter__.return_value
        if "vendors" in q and "vendor_code" in q:
            cur.fetchone.return_value = ("LH001", True)
        elif "vendor_operation_allowlist" in q:
            cur.fetchall.return_value = [
                {"source_vendor_code": "LH001", "target_vendor_code": "LH002", "operation_code": "GET_RECEIPT"},
            ]
        elif "operations" in q and "operation_contracts" not in q:
            cur.fetchall.return_value = [{"operation_code": "GET_RECEIPT", "canonical_version": "v1"}]
        elif "operation_contracts" in q and "vendor_operation_contracts" not in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": {"type": "object"}, "response_schema": {"type": "object"}},
            ]
        elif "vendor_operation_contracts" in q and "ANY" in q:
            cur.fetchall.return_value = []
        elif "vendor_operation_contracts" in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "is_active": True, "request_schema": {"type": "object"}, "response_schema": {"type": "object"}},
            ]
        elif "vendor_operation_mappings" in q:
            cur.fetchall.return_value = []
        elif "vendor_endpoints" in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_RECEIPT", "verification_status": "VERIFIED"},
            ]
        elif "request_schema" in q and "operation_contracts" in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": {"type": "object"}, "response_schema": {"type": "object"}},
            ]
        else:
            cur.fetchall.return_value = []

    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = execute_side_effect
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    event = _my_operations_event()
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    outbound = body["outbound"]
    assert len(outbound) == 1
    row = outbound[0]
    assert row["status"] == "ready"
    assert row["requestMappingStatus"] == "warning_optional_missing"
    assert row["responseMappingStatus"] == "warning_optional_missing"
    assert row["mappingStatus"] in ("OK", "OPTIONAL_MISSING_BOTH")
    assert "error_required_missing" not in str(row.get("issues", []))


def test_my_operations_no_vendor_returns_401() -> None:
    """When vendor code cannot be resolved: 401 AUTH_ERROR."""
    event = _my_operations_event()
    add_jwt_auth(event, "")

    with patch("vendor_registry_lambda._get_connection"):
        resp = handler(event, None)

    assert resp["statusCode"] == 401
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "AUTH_ERROR"


# --- Robustness tests (empty DB, partial config, direction-policy) ---


@patch("vendor_registry_lambda._get_connection")
def test_my_operations_empty_db_returns_200_empty_lists(
    mock_conn_ctx: MagicMock,
) -> None:
    """Empty DB (all queries return []) → 200 with outbound=[], inbound=[]."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = ("ACME", True)
    mock_cursor.fetchall.return_value = []
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    event = _my_operations_event()
    add_jwt_auth(event, "ACME")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["outbound"] == []
    assert body["inbound"] == []


@patch("vendor_registry_lambda._get_connection")
def test_my_operations_allowlist_only_no_contracts_mappings_endpoints(
    mock_conn_ctx: MagicMock,
) -> None:
    """Allowlist exists, but no contracts/mappings/endpoints → 200, at least one outbound entry (not ready), no 500."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    def execute_side_effect(query, params=()):
        q = str(query) if hasattr(query, "decode") else str(query)
        cur = mock_conn.cursor.return_value.__enter__.return_value
        if "vendors" in q and "vendor_code" in q:
            cur.fetchone.return_value = ("ACME", True)
        elif "vendor_operation_allowlist" in q:
            cur.fetchall.return_value = [
                {
                    "source_vendor_code": "ACME",
                    "target_vendor_code": "FOO",
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
        elif "operation_contracts" in q:
            cur.fetchall.return_value = [{"operation_code": "GET_WEATHER", "canonical_version": "v1"}]
        elif "vendor_operation_contracts" in q:
            cur.fetchall.return_value = []
        elif "vendor_operation_mappings" in q:
            cur.fetchall.return_value = []
        elif "vendor_endpoints" in q:
            cur.fetchall.return_value = []
        else:
            cur.fetchall.return_value = []

    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = execute_side_effect
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    event = _my_operations_event()
    add_jwt_auth(event, "ACME")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    outbound = body["outbound"]
    assert len(outbound) >= 1
    row = outbound[0]
    assert row["operationCode"] == "GET_WEATHER"
    assert row["direction"] == "outbound"
    assert row["status"] in ("needs_setup", "admin_pending", "needs_attention")
    assert body["inbound"] == []


@patch("vendor_registry_lambda._get_connection")
def test_my_operations_direction_policy_provider_receives_only(
    mock_conn_ctx: MagicMock,
) -> None:
    """PROVIDER_RECEIVES_ONLY: provider vendor (FOO) must not see op as outbound; can see inbound."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    def execute_side_effect(query, params=()):
        q = str(query) if hasattr(query, "decode") else str(query)
        cur = mock_conn.cursor.return_value.__enter__.return_value
        if "vendors" in q and "vendor_code" in q:
            cur.fetchone.return_value = ("FOO", True)
        elif "vendor_operation_allowlist" in q:
            cur.fetchall.return_value = [
                {
                    "source_vendor_code": "ACME",
                    "target_vendor_code": "FOO",
                    "is_any_source": False,
                    "is_any_target": False,
                    "operation_code": "GET_WEATHER",
                    "flow_direction": "BOTH",
                },
            ]
        elif "operations" in q and "operation_contracts" not in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_WEATHER", "canonical_version": "v1", "direction_policy": "PROVIDER_RECEIVES_ONLY", "is_active": True},
            ]
        elif "operation_contracts" in q:
            cur.fetchall.return_value = [{"operation_code": "GET_WEATHER", "canonical_version": "v1"}]
        elif "vendor_operation_contracts" in q:
            cur.fetchall.return_value = []
        elif "vendor_operation_mappings" in q:
            cur.fetchall.return_value = []
        elif "vendor_endpoints" in q:
            cur.fetchall.return_value = []
        else:
            cur.fetchall.return_value = []

    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = execute_side_effect
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    event = _my_operations_event()
    add_jwt_auth(event, "FOO")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    outbound = body["outbound"]
    inbound = body["inbound"]
    assert len(outbound) == 0
    assert len(inbound) >= 1
    assert inbound[0]["operationCode"] == "GET_WEATHER"
    assert inbound[0]["direction"] == "inbound"


@patch("vendor_registry_lambda._get_connection")
def test_my_operations_direction_policy_two_way(
    mock_conn_ctx: MagicMock,
) -> None:
    """TWO_WAY: when allowlist allows both, outbound and inbound both appear."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    def execute_side_effect(query, params=()):
        q = str(query) if hasattr(query, "decode") else str(query)
        cur = mock_conn.cursor.return_value.__enter__.return_value
        if "vendors" in q and "vendor_code" in q:
            cur.fetchone.return_value = ("ACME", True)
        elif "vendor_operation_allowlist" in q:
            cur.fetchall.return_value = [
                {
                    "source_vendor_code": "ACME",
                    "target_vendor_code": "BAR",
                    "is_any_source": False,
                    "is_any_target": False,
                    "operation_code": "GET_WEATHER",
                    "flow_direction": "BOTH",
                },
                {
                    "source_vendor_code": "BAR",
                    "target_vendor_code": "ACME",
                    "is_any_source": False,
                    "is_any_target": False,
                    "operation_code": "GET_WEATHER",
                    "flow_direction": "BOTH",
                },
            ]
        elif "operations" in q and "operation_contracts" not in q:
            cur.fetchall.return_value = [
                {"operation_code": "GET_WEATHER", "canonical_version": "v1", "direction_policy": "TWO_WAY", "is_active": True},
            ]
        elif "operation_contracts" in q:
            cur.fetchall.return_value = [{"operation_code": "GET_WEATHER", "canonical_version": "v1"}]
        elif "vendor_operation_contracts" in q:
            cur.fetchall.return_value = []
        elif "vendor_operation_mappings" in q:
            cur.fetchall.return_value = []
        elif "vendor_endpoints" in q:
            cur.fetchall.return_value = []
        else:
            cur.fetchall.return_value = []

    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = execute_side_effect
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    event = _my_operations_event()
    add_jwt_auth(event, "ACME")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    outbound = body["outbound"]
    inbound = body["inbound"]
    assert len(outbound) >= 1
    assert len(inbound) >= 1
    out_op = next(r for r in outbound if r["operationCode"] == "GET_WEATHER")
    in_op = next(r for r in inbound if r["operationCode"] == "GET_WEATHER")
    assert out_op["direction"] == "outbound"
    assert in_op["direction"] == "inbound"
