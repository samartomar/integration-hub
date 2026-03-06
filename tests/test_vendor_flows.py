"""Unit tests for Vendor Registry Lambda - Flow Builder and Operation Mappings endpoints."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from vendor_registry_lambda import handler  # noqa: E402
from vendor_registry_jwt import add_jwt_auth  # noqa: E402


def _event(method: str, path: str, body: dict | None = None) -> dict:
    """Build a minimal Lambda event for vendor API."""
    return {
        "path": path,
        "rawPath": path,
        "httpMethod": method,
        "pathParameters": {},
        "queryStringParameters": {},
        "requestContext": {"http": {"method": method}, "requestId": "test-req-id"},
        "headers": {},
        "body": json.dumps(body) if body is not None else None,
    }


def _flows_event(
    method: str,
    path: str,
    body: dict | None = None,
) -> dict:
    return {
        "path": path,
        "rawPath": path,
        "httpMethod": method,
        "pathParameters": {},
        "queryStringParameters": {},
        "requestContext": {"http": {"method": method}, "requestId": "test-req-id"},
        "headers": {},
        "body": json.dumps(body) if body is not None else None,
    }


@patch("vendor_registry_lambda._get_connection")
def test_flows_get_returns_combined_data(
    mock_conn_ctx: MagicMock,
) -> None:
    """GET /v1/vendor/flows/GET_RECEIPT/v1 returns canonical + vendor + mappings + layout."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    mapping_results = iter([
        {"mapping": {"txn_id": "$.transactionId"}},
        {"mapping": {"receipt": "$.result"}},
    ])

    def execute_side_effect(query, params=()):
        q = str(query) if hasattr(query, "decode") else str(query)
        cur = mock_conn.cursor.return_value.__enter__.return_value
        cur.fetchall.return_value = []
        cur.fetchone.side_effect = None
        if "vendors" in q and "vendor_code" in q:
            cur.fetchone.return_value = ("LH001", True)
        elif "vendor_supported_operations" in q or "vendor_operation_allowlist" in q:
            cur.fetchone.return_value = {1: 1}
        elif "operation_contracts" in q and "vendor_operation_contracts" not in q:
            cur.fetchone.return_value = {
                "request_schema": {"type": "object", "properties": {"transactionId": {"type": "string"}}},
                "response_schema": {"type": "object", "properties": {"receipt": {"type": "string"}}},
            }
        elif "vendor_operation_contracts" in q:
            cur.fetchone.return_value = {
                "request_schema": {"type": "object", "properties": {"txn_id": {"type": "string"}}},
                "response_schema": {"type": "object", "properties": {"result": {"type": "string"}}},
            }
        elif "vendor_operation_mappings" in q:
            try:
                cur.fetchone.return_value = next(mapping_results)
            except StopIteration:
                cur.fetchone.return_value = None
        elif "vendor_flow_layouts" in q:
            cur.fetchone.return_value = {"layout": {"nodes": []}, "visual_model": None}
        else:
            cur.fetchone.return_value = None

    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = execute_side_effect
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    event = _flows_event("GET", "/v1/vendor/flows/GET_RECEIPT/v1")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["operationCode"] == "GET_RECEIPT"
    assert body["version"] == "v1"
    assert "canonicalRequestSchema" in body
    assert "canonicalResponseSchema" in body
    assert body["requestMapping"] == {"txn_id": "$.transactionId"}
    assert body["responseMapping"] == {"receipt": "$.result"}
    assert "endpoint" in body


@patch("vendor_registry_lambda._get_connection")
def test_flows_put_updates_contracts_mappings_layout(
    mock_conn_ctx: MagicMock,
) -> None:
    """PUT /v1/vendor/flows/GET_RECEIPT/v1 updates vendor contract, mappings, layout."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    call_count = {"execute": 0}

    get_flow_mapping_iter = iter([
        {"mapping": {"txn_id": "$.transactionId"}},
        {"mapping": {"receipt": "$.result"}},
    ])

    def execute_side_effect(query, params=()):
        q = str(query) if hasattr(query, "decode") else str(query)
        cur = mock_conn.cursor.return_value.__enter__.return_value
        cur.fetchall.return_value = []
        cur.rowcount = 1
        call_count["execute"] += 1

        if "vendors" in q and "vendor_code" in q:
            cur.fetchone.return_value = ("LH001", True)
        elif "vendor_supported_operations" in q or "vendor_operation_allowlist" in q:
            cur.fetchone.return_value = {1: 1}
        elif "operation_contracts" in q and "vendor_operation_contracts" not in q:
            cur.fetchone.return_value = {"request_schema": {}, "response_schema": {}}
        elif "vendor_operation_contracts" in q and "INSERT" not in q:
            cur.fetchone.return_value = {"request_schema": {}, "response_schema": {}}
        elif "vendor_operation_mappings" in q and "DELETE" not in q and "INSERT" not in q:
            if "SELECT mapping" in q:
                # _load_flow_mapping (used by GET flow) - return mapping row
                try:
                    cur.fetchone.return_value = next(get_flow_mapping_iter)
                except StopIteration:
                    cur.fetchone.return_value = None
            else:
                # q_find in _upsert_vendor_mapping (SELECT id, is_active) - return None to take INSERT path
                cur.fetchone.return_value = None
        elif "vendor_flow_layouts" in q and "INSERT" not in q:
            cur.fetchone.return_value = None
        elif "vendor_operation_contracts" in q and "INSERT" in q:
            cur.fetchone.return_value = {
                "id": "c1",
                "vendor_code": "LH001",
                "operation_code": "GET_RECEIPT",
                "canonical_version": "v1",
            }
        elif "vendor_operation_mappings" in q and "INSERT" in q:
            cur.fetchone.return_value = {"id": "m1"}
        elif "vendor_change_requests" in q:
            cur.fetchone.return_value = {"id": "cr-flow-123"}
        else:
            cur.fetchone.return_value = None

    mock_cursor = MagicMock()
    mock_cursor.rowcount = 1
    mock_cursor.execute.side_effect = execute_side_effect
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    payload = {
        "visualModel": {"nodes": [], "edges": []},
        "requestMapping": {"txn_id": "$.transactionId"},
        "responseMapping": {"receipt": "$.result"},
    }
    event = _flows_event("PUT", "/v1/vendor/flows/GET_RECEIPT/v1", payload)
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 202
    body = json.loads(resp["body"])
    assert body["status"] == "PENDING"
    assert "changeRequestId" in body


@patch("vendor_registry_lambda._get_connection")
def test_flows_test_post_canonical_to_canonical(
    mock_conn_ctx: MagicMock,
) -> None:
    """POST .../test runs canonical -> vendor (stubbed) -> canonical loop."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    mapping_fetchone_results = iter([
        {"mapping": {"txn_id": "$.transactionId"}},
        {"mapping": {"receipt": "$.result"}},
    ])

    def execute_side_effect(query, params=()):
        q = str(query) if hasattr(query, "decode") else str(query)
        cur = mock_conn.cursor.return_value.__enter__.return_value
        cur.fetchall.return_value = []
        if "vendors" in q and "vendor_code" in q:
            cur.fetchone.return_value = ("LH001", True)
        elif "vendor_supported_operations" in q or "vendor_operation_allowlist" in q:
            cur.fetchone.return_value = {1: 1}
        elif "vendor_operation_mappings" in q:
            try:
                cur.fetchone.return_value = next(mapping_fetchone_results)
            except StopIteration:
                cur.fetchone.return_value = None
        else:
            cur.fetchone.return_value = None

    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = execute_side_effect
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    payload = {"canonicalRequest": {"transactionId": "TXN-001"}}
    event = _flows_event("POST", "/v1/vendor/flows/GET_RECEIPT/v1/test", payload)
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["canonicalRequest"] == {"transactionId": "TXN-001"}
    assert body["vendorRequest"] == {"txn_id": "TXN-001"}
    assert body["vendorResponse"]["status"] == "OK"
    assert body["vendorResponse"]["receiptId"] == "R-TXN-001"
    assert body["vendorResponse"]["result"] == "R-TXN-001"
    assert body["canonicalResponse"] == {"receipt": "R-TXN-001"}
    assert body["errors"]["mappingRequest"] == []
    assert body["errors"]["downstream"] == []
    assert body["errors"]["mappingResponse"] == []


@patch("vendor_registry_lambda._get_connection")
def test_flows_test_post_uses_body_mapping_when_provided(
    mock_conn_ctx: MagicMock,
) -> None:
    """POST .../test uses requestMapping/responseMapping from body when provided (unsaved edits)."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    def execute_side_effect(query, params=()):
        q = str(query) if hasattr(query, "decode") else str(query)
        cur = mock_conn.cursor.return_value.__enter__.return_value
        cur.fetchall.return_value = []
        if "vendors" in q and "vendor_code" in q:
            cur.fetchone.return_value = ("LH001", True)
        elif "vendor_supported_operations" in q or "vendor_operation_allowlist" in q:
            cur.fetchone.return_value = {1: 1}
        else:
            cur.fetchone.return_value = None

    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = execute_side_effect
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    payload = {
        "canonicalRequest": {"transactionId": "TXN-002"},
        "requestMapping": {"txn_id": "$.transactionId"},
        "responseMapping": {"receipt": "$.result"},
    }
    event = _flows_event("POST", "/v1/vendor/flows/GET_RECEIPT/v1/test", payload)
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["vendorRequest"] == {"txn_id": "TXN-002"}
    assert body["vendorResponse"]["result"] == "R-TXN-002"
    assert body["canonicalResponse"] == {"receipt": "R-TXN-002"}


# --- Operation Mappings (GET/PUT /v1/vendor/operations/{op}/{ver}/mappings) ---


@patch("vendor_registry_lambda._get_connection")
def test_operation_mappings_get_returns_simplified_shape(
    mock_conn_ctx: MagicMock,
) -> None:
    """GET /v1/vendor/operations/GET_RECEIPT/v1/mappings returns request/response with mapping JSON."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    fetchone_results = iter([
        {"mapping": {"txn_id": "$.transactionId"}},
        {"mapping": {"receipt": "$.result"}},
    ])

    def execute_side_effect(query, params=()):
        q = str(query) if hasattr(query, "decode") else str(query)
        cur = mock_conn.cursor.return_value.__enter__.return_value
        cur.fetchall.return_value = []
        if "vendors" in q and "vendor_code" in q:
            cur.fetchone.return_value = ("LH001", True)
        elif "vendor_operation_mappings" in q and "SELECT mapping" in q:
            try:
                cur.fetchone.return_value = next(fetchone_results)
            except StopIteration:
                cur.fetchone.return_value = None
        else:
            cur.fetchone.return_value = None

    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = execute_side_effect
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    event = _event("GET", "/v1/vendor/operations/GET_RECEIPT/v1/mappings")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["operationCode"] == "GET_RECEIPT"
    assert body["canonicalVersion"] == "v1"
    assert body["request"]["direction"] == "CANONICAL_TO_TARGET_REQUEST"
    assert body["request"]["mapping"] == {"txn_id": "$.transactionId"}
    assert body["response"]["direction"] == "TARGET_TO_CANONICAL_RESPONSE"
    assert body["response"]["mapping"] == {"receipt": "$.result"}


@patch("vendor_registry_lambda._get_connection")
def test_operation_mappings_get_returns_none_when_missing(
    mock_conn_ctx: MagicMock,
) -> None:
    """GET returns usesCanonical=True when no mappings exist (canonical mode)."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    def execute_side_effect(query, params=()):
        q = str(query) if hasattr(query, "decode") else str(query)
        cur = mock_conn.cursor.return_value.__enter__.return_value
        cur.fetchall.return_value = []
        if "vendors" in q and "vendor_code" in q:
            cur.fetchone.return_value = ("LH001", True)
        else:
            cur.fetchone.return_value = None

    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = execute_side_effect
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    event = _event("GET", "/v1/vendor/operations/GET_RECEIPT/v1/mappings")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["usesCanonicalRequest"] is True
    assert body["usesCanonicalResponse"] is True
    assert body["request"]["usesCanonical"] is True
    assert body["request"]["mapping"] is None
    assert body["response"]["usesCanonical"] is True
    assert body["response"]["mapping"] is None


@patch("vendor_registry_lambda._get_connection")
def test_operation_mappings_put_upserts_both(
    mock_conn_ctx: MagicMock,
) -> None:
    """PUT /v1/vendor/operations/GET_RECEIPT/v1/mappings upserts request + response mappings."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    fetchone_results = [
        ("LH001", True),  # vendor validation
        {1: 1},  # _vendor_has_operation_access (supported_operations)
        (True,),  # is_feature_gated (enabled=True) - row[0] must be truthy for gated
        {"id": "cr-mappings-123"},  # _create_vendor_change_request RETURNING
    ]

    def execute_side_effect(query, params=()):
        cur = mock_conn.cursor.return_value.__enter__.return_value
        cur.rowcount = 1
        cur.fetchall.return_value = []

    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = execute_side_effect
    mock_cursor.fetchone.side_effect = fetchone_results
    mock_cursor.__enter__.return_value = mock_cursor
    mock_cursor.__exit__.return_value = None
    mock_conn.cursor.return_value = mock_cursor

    payload = {
        "request": {"direction": "CANONICAL_TO_TARGET_REQUEST", "mapping": {"txnId": "$.transactionId"}},
        "response": {"direction": "TARGET_TO_CANONICAL_RESPONSE", "mapping": {"receipt": "$.result"}},
    }
    event = _event("PUT", "/v1/vendor/operations/GET_RECEIPT/v1/mappings", payload)
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 202
    body = json.loads(resp["body"])
    assert body["status"] == "PENDING"
    assert "changeRequestId" in body
