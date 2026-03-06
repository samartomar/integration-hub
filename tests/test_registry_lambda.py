"""Unit tests for Registry Lambda - Contract Read API and GET list endpoints."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from registry_lambda import (  # noqa: E402
    handler,
    _decode_cursor,
    _encode_cursor,
    _validate_flow_direction,
    derive_flow_direction_for_operation,
)

# Auth: Registry routes require JWT authorizer (Okta)
JWT_AUTHORIZER = {"principalId": "okta|test", "jwt": {"claims": {"sub": "okta|test", "aud": "api://default", "groups": ["admins", "admin"]}}}
AUTH_REQUEST_CONTEXT = {"http": {"method": "GET"}, "authorizer": JWT_AUTHORIZER}
AUTH_REQUEST_CONTEXT_POST = {"http": {"method": "POST"}, "requestId": "test-req-id", "authorizer": JWT_AUTHORIZER}


def _mock_cursor(conn_mock, rows: list) -> None:
    """Configure mock connection to return rows from fetchall."""
    conn_mock.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchall.return_value = rows


def _contracts_get_event(
    operation_code: str | None = None,
    canonical_version: str | None = None,
    is_active: str | None = None,
) -> dict:
    """Build GET /v1/registry/contracts event with optional query params."""
    params = {}
    if operation_code is not None:
        params["operationCode"] = operation_code
    if canonical_version is not None:
        params["canonicalVersion"] = canonical_version
    if is_active is not None:
        params["isActive"] = is_active
    return {
        "path": "/v1/registry/contracts",
        "rawPath": "/v1/registry/contracts",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": params,
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _readiness_get_event(
    vendor_code: str = "LH002",
    operation_code: str | None = None,
) -> dict:
    """Build GET /v1/registry/readiness event."""
    params: dict[str, str] = {"vendorCode": vendor_code}
    if operation_code:
        params["operationCode"] = operation_code
    return {
        "path": "/v1/registry/readiness",
        "rawPath": "/v1/registry/readiness",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": params,
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _contracts_post_event(
    operation_code: str = "GET_RECEIPT",
    canonical_version: str = "v1",
    request_schema: dict | None = None,
    response_schema: dict | None = None,
    is_active: bool = True,
) -> dict:
    """Build POST /v1/registry/contracts event."""
    schema = request_schema or {"type": "object", "required": ["transactionId"], "properties": {"transactionId": {"type": "string"}}}
    body = {
        "operationCode": operation_code,
        "canonicalVersion": canonical_version,
        "requestSchema": schema,
    }
    if response_schema is not None:
        body["responseSchema"] = response_schema
    if is_active is not None:
        body["isActive"] = is_active
    return {
        "path": "/v1/registry/contracts",
        "rawPath": "/v1/registry/contracts",
        "httpMethod": "POST",
        "headers": {},
        "body": json.dumps(body),
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT_POST,
    }


@patch("registry_lambda._get_connection")
def test_get_contracts_returns_list_with_contracts(mock_conn_ctx) -> None:
    """GET /v1/registry/contracts returns contracts list with optional filters."""
    schema = {"type": "object", "required": ["transactionId"], "properties": {"transactionId": {"type": "string"}}}
    _mock_cursor(mock_conn_ctx, [
        {
            "id": "c1",
            "operation_code": "GET_RECEIPT",
            "canonical_version": "v1",
            "request_schema": schema,
            "response_schema": None,
            "is_active": True,
            "created_at": "2024-01-01",
            "updated_at": "2024-01-02",
        },
    ])

    event = _contracts_get_event(operation_code="GET_RECEIPT", canonical_version="v1")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "contracts" in body
    assert len(body["contracts"]) == 1
    assert body["contracts"][0]["operationCode"] == "GET_RECEIPT"
    assert body["contracts"][0]["canonicalVersion"] == "v1"
    assert body["contracts"][0]["requestSchema"] == schema
    assert body["contracts"][0]["isActive"] is True
    assert body["contracts"][0]["createdAt"] is not None
    assert body["contracts"][0]["updatedAt"] is not None


@patch("registry_lambda._get_connection")
def test_get_contracts_filtering_returns_empty_when_no_match(mock_conn_ctx) -> None:
    """GET with filters returns empty contracts list when no match."""
    _mock_cursor(mock_conn_ctx, [])

    event = _contracts_get_event(operation_code="UNKNOWN_OP", canonical_version="v99")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["contracts"] == []


@patch("registry_lambda._get_connection")
def test_get_contracts_filtering_works(mock_conn_ctx) -> None:
    """GET with operationCode/canonicalVersion/isActive filters returns matching contracts."""
    schema = {"type": "object"}
    _mock_cursor(mock_conn_ctx, [
        {"id": "a", "operation_code": "OP1", "canonical_version": "v1", "request_schema": schema, "response_schema": None, "is_active": True, "created_at": "2024-01-01", "updated_at": "2024-01-02"},
    ])

    event = _contracts_get_event(operation_code="OP1", canonical_version="v1", is_active="true")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert len(body["contracts"]) == 1
    assert body["contracts"][0]["operationCode"] == "OP1"


@patch("registry_lambda._get_connection")
def test_post_contracts_create_works(mock_conn_ctx) -> None:
    """POST /v1/registry/contracts create (new row) works. Uses SELECT-then-INSERT (no ON CONFLICT)."""
    schema = {"type": "object", "required": ["transactionId"], "properties": {"transactionId": {"type": "string"}}}
    returned_row = {
        "id": "uuid-1",
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "request_schema": schema,
        "response_schema": None,
        "is_active": True,
        "created_at": "2024-01-01",
        "updated_at": "2024-01-02",
    }
    cur_mock = mock_conn_ctx.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur_mock.execute = lambda *a, **k: None
    # 1st fetchone: SELECT finds no active row -> None; 2nd: INSERT RETURNING -> row
    cur_mock.fetchone.side_effect = [None, returned_row]
    cur_mock.rowcount = 1

    event = _contracts_post_event(operation_code="GET_RECEIPT", canonical_version="v1", request_schema=schema)
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "contract" in body
    assert body["contract"]["operationCode"] == "GET_RECEIPT"
    assert body["contract"]["canonicalVersion"] == "v1"
    assert body["contract"]["requestSchema"] == schema


@patch("registry_lambda._get_connection")
def test_post_contracts_update_works(mock_conn_ctx) -> None:
    """POST /v1/registry/contracts update (existing active row) works. Uses SELECT-then-UPDATE."""
    updated_schema = {"type": "object", "properties": {"transactionId": {"type": "string"}}}
    returned_row = {
        "id": "uuid-1",
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "request_schema": updated_schema,
        "response_schema": {"type": "object"},
        "is_active": True,
        "created_at": "2024-01-01",
        "updated_at": "2024-01-03",
    }
    cur_mock = mock_conn_ctx.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur_mock.execute = lambda *a, **k: None
    # 1st fetchone: SELECT finds existing row with id; 2nd: UPDATE RETURNING -> updated row
    cur_mock.fetchone.side_effect = [{"id": "uuid-1"}, returned_row]

    event = _contracts_post_event(
        operation_code="GET_RECEIPT",
        canonical_version="v1",
        request_schema=updated_schema,
        response_schema={"type": "object"},
    )
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["contract"]["operationCode"] == "GET_RECEIPT"
    assert body["contract"]["canonicalVersion"] == "v1"
    assert body["contract"]["requestSchema"] == updated_schema
    assert body["contract"]["responseSchema"] == {"type": "object"}


@patch("registry_lambda._get_connection")
def test_post_contracts_create_get_weather_v1(mock_conn_ctx) -> None:
    """POST /v1/registry/contracts creates GET_WEATHER v1 contract (no ON CONFLICT, partial index safe)."""
    schema = {"type": "object", "properties": {"city": {"type": "string"}}}
    returned_row = {
        "id": "uuid-weather",
        "operation_code": "GET_WEATHER",
        "canonical_version": "v1",
        "request_schema": schema,
        "response_schema": None,
        "is_active": True,
        "created_at": "2024-01-01",
        "updated_at": "2024-01-01",
    }
    cur_mock = mock_conn_ctx.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur_mock.execute = lambda *a, **k: None
    cur_mock.fetchone.side_effect = [None, returned_row]

    event = _contracts_post_event(operation_code="GET_WEATHER", canonical_version="v1", request_schema=schema)
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["contract"]["operationCode"] == "GET_WEATHER"
    assert body["contract"]["canonicalVersion"] == "v1"
    assert body["contract"]["isActive"] is True


def _set_canonical_version_post_event(
    operation_code: str = "GET_WEATHER",
    canonical_version: str = "v2",
) -> dict:
    """Build POST /v1/registry/operations/{operationCode}/canonical-version event."""
    return {
        "path": f"/v1/registry/operations/{operation_code}/canonical-version",
        "rawPath": f"/v1/registry/operations/{operation_code}/canonical-version",
        "httpMethod": "POST",
        "headers": {},
        "body": json.dumps({"canonicalVersion": canonical_version}),
        "pathParameters": {"operationCode": operation_code},
        "requestContext": AUTH_REQUEST_CONTEXT_POST,
    }


@patch("registry_lambda._get_connection")
def test_set_canonical_version_success(mock_conn_ctx) -> None:
    """POST /v1/registry/operations/{op}/canonical-version updates operations.canonical_version."""
    from datetime import datetime

    cur_mock = mock_conn_ctx.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur_mock.execute = lambda *a, **k: None
    # 1st: operation exists; 2nd: contract exists; 3rd: UPDATE RETURNING
    cur_mock.fetchone.side_effect = [
        {"operation_code": "GET_WEATHER"},
        {"1": 1},
        {
            "operation_code": "GET_WEATHER",
            "canonical_version": "v2",
            "updated_at": datetime(2024, 1, 15),
        },
    ]

    event = _set_canonical_version_post_event(operation_code="GET_WEATHER", canonical_version="v2")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["operationCode"] == "GET_WEATHER"
    assert body["canonicalVersion"] == "v2"


@patch("registry_lambda._get_connection")
def test_set_canonical_version_no_active_contract(mock_conn_ctx) -> None:
    """POST set canonical version returns 400 when no active contract for version."""
    cur_mock = mock_conn_ctx.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur_mock.execute = lambda *a, **k: None
    cur_mock.fetchone.side_effect = [
        {"operation_code": "GET_WEATHER"},
        None,
    ]

    event = _set_canonical_version_post_event(operation_code="GET_WEATHER", canonical_version="v99")
    resp = handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body["error"]["code"] == "NO_ACTIVE_CONTRACT_FOR_VERSION"


def test_post_contracts_missing_request_schema_returns_validation_error() -> None:
    """POST without requestSchema returns 400 VALIDATION_ERROR."""
    event = _contracts_post_event()
    event["body"] = json.dumps({"operationCode": "GET_RECEIPT", "canonicalVersion": "v1"})

    resp = handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "requestSchema" in body["error"]["message"]


def test_post_contracts_missing_operation_code_returns_validation_error() -> None:
    """POST without operationCode returns 400."""
    event = _contracts_post_event()
    event["body"] = json.dumps({"canonicalVersion": "v1", "requestSchema": {"type": "object"}})

    resp = handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "operationCode" in body["error"]["message"]


def test_post_contracts_missing_canonical_version_returns_validation_error() -> None:
    """POST without canonicalVersion returns 400."""
    event = _contracts_post_event()
    event["body"] = json.dumps({"operationCode": "GET_RECEIPT", "requestSchema": {"type": "object"}})

    resp = handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "canonicalVersion" in body["error"]["message"]


def test_post_contracts_invalid_request_schema_returns_validation_error() -> None:
    """POST with non-object requestSchema returns 400."""
    event = _contracts_post_event()
    event["body"] = json.dumps({"operationCode": "GET_RECEIPT", "canonicalVersion": "v1", "requestSchema": "not-an-object"})

    resp = handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "requestSchema" in body["error"]["message"]


@patch("registry_lambda._write_audit_event")
@patch("registry_lambda._get_connection")
def test_post_contracts_writes_audit_event(mock_conn_ctx, mock_audit) -> None:
    """POST contracts writes canonical_contract_upsert audit event with COMPANY_A and is_active."""
    returned_row = {
        "id": "uuid-1",
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "request_schema": {},
        "response_schema": None,
        "is_active": True,
        "created_at": "2024-01-01",
        "updated_at": "2024-01-02",
    }
    cur_mock = mock_conn_ctx.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur_mock.execute = lambda *a, **k: None
    cur_mock.fetchone.return_value = returned_row

    event = _contracts_post_event()
    handler(event, None)

    mock_audit.assert_called_once()
    call = mock_audit.call_args
    kwargs = call[1]
    assert kwargs["action"] == "canonical_contract_upsert"
    assert kwargs["vendor_code"] == "COMPANY_A"
    details = kwargs["details"]
    assert details["operation_code"] == "GET_RECEIPT"
    assert details["canonical_version"] == "v1"
    assert details["is_active"] is True


# --- ListOperations API ---


def _operations_event(
    is_active: str = "true",
    source_vendor: str | None = None,
    target_vendor: str | None = None,
) -> dict:
    """Build GET /v1/registry/operations event with query params."""
    params = {"isActive": is_active}
    if source_vendor:
        params["sourceVendor"] = source_vendor
    if target_vendor:
        params["targetVendor"] = target_vendor
    return {
        "path": "/v1/registry/operations",
        "rawPath": "/v1/registry/operations",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": params,
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


@patch("registry_lambda._get_connection")
def test_get_operations_returns_list(mock_conn_ctx) -> None:
    """GET /v1/registry/operations returns operations list."""
    mock_conn_ctx.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchall.return_value = [
        {"operation_code": "GET_RECEIPT", "description": "Get receipt", "canonical_version": "v1"},
        {"operation_code": "SEND_RECEIPT", "description": "Send receipt", "canonical_version": "v1"},
    ]

    event = _operations_event()
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "items" in body
    assert len(body["items"]) == 2
    assert body["items"][0]["operationCode"] == "GET_RECEIPT"
    assert body["items"][0]["description"] == "Get receipt"
    assert body["items"][0]["canonicalVersion"] == "v1"


@patch("registry_lambda._get_connection")
def test_get_operations_with_allowlist_filter(mock_conn_ctx) -> None:
    """GET with sourceVendor and targetVendor filters by allowlist."""
    mock_conn_ctx.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchall.return_value = [
        {"operation_code": "GET_RECEIPT", "description": "Get receipt", "canonical_version": "v1"},
    ]

    event = _operations_event(source_vendor="LH001", target_vendor="LH002")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert len(body["items"]) == 1
    assert body["items"][0]["operationCode"] == "GET_RECEIPT"


def test_get_operations_partial_vendor_params_returns_error() -> None:
    """sourceVendor without targetVendor (or vice versa) returns 400."""
    event = _operations_event(source_vendor="LH001")
    resp = handler(event, None)
    assert resp["statusCode"] == 400
    assert "sourceVendorCode and targetVendorCode" in json.loads(resp["body"])["error"]["message"]


# --- Auth guard ---


def test_registry_get_missing_jwt_returns_401() -> None:
    """GET /v1/registry/vendors without JWT authorizer returns 401 AUTH_ERROR."""
    event = {
        "path": "/v1/registry/vendors",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "requestContext": {},
    }
    resp = handler(event, None)
    assert resp["statusCode"] == 401
    body = json.loads(resp["body"])
    assert body["error"]["code"] == "AUTH_ERROR"


def _mission_control_topology_event(
    request_context: dict | None = None,
) -> dict:
    return {
        "path": "/v1/registry/mission-control/topology",
        "rawPath": "/v1/registry/mission-control/topology",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": request_context if request_context is not None else AUTH_REQUEST_CONTEXT,
    }


def _mission_control_activity_event(
    query: dict | None = None,
    request_context: dict | None = None,
) -> dict:
    return {
        "path": "/v1/registry/mission-control/activity",
        "rawPath": "/v1/registry/mission-control/activity",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": query or {},
        "pathParameters": {},
        "requestContext": request_context if request_context is not None else AUTH_REQUEST_CONTEXT,
    }


def test_mission_control_topology_missing_jwt_returns_401() -> None:
    event = _mission_control_topology_event(request_context={})
    resp = handler(event, None)
    assert resp["statusCode"] == 401
    assert json.loads(resp["body"])["error"]["code"] == "AUTH_ERROR"


def test_mission_control_topology_non_admin_role_returns_403(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_REQUIRED_ROLE", "integrationhub-admins")
    request_context = {
        "http": {"method": "GET"},
        "authorizer": {"principalId": "okta|test", "jwt": {"claims": {"sub": "okta|test", "aud": "api://default", "groups": ["viewer"]}}},
    }
    event = _mission_control_topology_event(request_context=request_context)
    resp = handler(event, None)
    assert resp["statusCode"] == 403
    assert json.loads(resp["body"])["error"]["code"] == "AUTH_ERROR"


@patch("registry_lambda._get_connection")
def test_get_mission_control_topology_returns_metadata_only(mock_conn) -> None:
    cur_mock = mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur_mock.fetchall.side_effect = [
        [{"vendor_code": "LH001", "vendor_name": "Vendor 1"}],
        [{
            "source_vendor_code": "LH001",
            "target_vendor_code": "LH002",
            "operation_code": "GET_RECEIPT",
            "flow_direction": "OUTBOUND",
        }],
    ]

    resp = handler(_mission_control_topology_event(), None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["nodes"][0]["vendorCode"] == "LH001"
    assert body["edges"][0]["operationCode"] == "GET_RECEIPT"
    dumped = json.dumps(body).lower()
    assert "request_body" not in dumped
    assert "response_body" not in dumped
    assert "debug_payload" not in dumped


@patch("registry_lambda._get_connection")
def test_get_mission_control_activity_returns_metadata_only(mock_conn) -> None:
    cur_mock = mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur_mock.fetchall.side_effect = [
        [{
            "created_at": "2026-03-05T12:00:00Z",
            "transaction_id": "tx-1",
            "correlation_id": "corr-1",
            "source_vendor": "LH001",
            "target_vendor": "LH002",
            "operation": "GET_RECEIPT",
            "status": "success",
            "http_status": 200,
        }],
        [{
            "occurred_at": "2026-03-05T12:00:01Z",
            "transaction_id": "tx-2",
            "correlation_id": "corr-2",
            "vendor_code": "LH001",
            "target_vendor_code": "LH003",
            "operation_code": "GET_RECEIPT",
            "decision_code": "ACCESS_DENIED",
            "http_status": 403,
        }],
    ]

    resp = handler(_mission_control_activity_event(), None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["count"] == 2
    assert {item["stage"] for item in body["items"]} == {"EXECUTE_SUCCESS", "POLICY_DENY"}
    dumped = json.dumps(body).lower()
    assert "request_body" not in dumped
    assert "response_body" not in dumped
    assert "debug_payload" not in dumped


@patch("registry_lambda._get_connection")
def test_get_mission_control_activity_lookback_clamps_to_60(mock_conn) -> None:
    cur_mock = mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur_mock.fetchall.side_effect = [[], []]

    resp = handler(_mission_control_activity_event(query={"lookbackMinutes": "999"}), None)
    assert resp["statusCode"] == 200
    first_call_args = cur_mock.execute.call_args_list[0][0][1]
    assert first_call_args[0] == 60
    body = json.loads(resp["body"])
    assert body["lookbackMinutes"] == 60


# --- Limit clamping ---


@patch("registry_lambda._get_connection")
def test_limit_over_max_returns_validation_error(mock_conn) -> None:
    """limit=300 returns 400 VALIDATION_ERROR (max 200)."""
    _mock_cursor(mock_conn, [{"id": "x", "vendor_code": "LH001", "vendor_name": "A", "is_active": True, "created_at": "2024-01-01", "updated_at": None}])
    event = {
        "path": "/v1/registry/vendors",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {"limit": "300"},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }
    resp = handler(event, None)
    assert resp["statusCode"] == 400
    assert json.loads(resp["body"])["error"]["code"] == "VALIDATION_ERROR"
    assert "200" in json.loads(resp["body"])["error"]["message"]


@patch("registry_lambda._get_connection")
def test_limit_one_works(mock_conn) -> None:
    """limit=1 returns at most 1 item."""
    _mock_cursor(mock_conn, [{"id": "a", "vendor_code": "LH001", "vendor_name": "A", "is_active": True, "created_at": "2024-01-01", "updated_at": None}])
    event = {
        "path": "/v1/registry/vendors",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {"limit": "1"},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert len(body["items"]) <= 1
    assert "nextCursor" in body


# --- Cursor encode/decode ---


def test_cursor_encode_decode_roundtrip() -> None:
    """_encode_cursor and _decode_cursor roundtrip correctly."""
    created_at = "2024-01-15T10:30:00+00:00"
    row_id = "550e8400-e29b-41d4-a716-446655440000"
    encoded = _encode_cursor(created_at, row_id)
    assert isinstance(encoded, str)
    decoded = _decode_cursor(encoded)
    assert decoded == (created_at, row_id)


def test_cursor_decode_invalid_returns_none() -> None:
    """Invalid cursor returns None."""
    assert _decode_cursor("") is None
    assert _decode_cursor("   ") is None
    assert _decode_cursor("not-valid-base64!!!") is None
    # Malformed: missing pipe
    bad = base64.urlsafe_b64encode(b"2024-01-01").decode()
    assert _decode_cursor(bad) is None


def test_cursor_decode_valid_format() -> None:
    """Valid cursor decodes to (created_at_iso, id)."""
    raw = "2024-01-01T00:00:00Z|abc-123"
    enc = base64.urlsafe_b64encode(raw.encode()).decode()
    assert _decode_cursor(enc) == ("2024-01-01T00:00:00Z", "abc-123")


# --- flow_direction validation ---


def test_validate_flow_direction_accepts_valid_values() -> None:
    """_validate_flow_direction accepts INBOUND, OUTBOUND, BOTH."""
    assert _validate_flow_direction("INBOUND") == "INBOUND"
    assert _validate_flow_direction("OUTBOUND") == "OUTBOUND"
    assert _validate_flow_direction("BOTH") == "BOTH"
    assert _validate_flow_direction("inbound") == "INBOUND"
    assert _validate_flow_direction("outbound") == "OUTBOUND"
    assert _validate_flow_direction("both") == "BOTH"


def test_validate_flow_direction_raises_on_none_or_empty() -> None:
    """_validate_flow_direction raises ValueError for None or empty; callers handle defaulting."""
    with pytest.raises(ValueError, match="flowDirection must be one of"):
        _validate_flow_direction(None)
    with pytest.raises(ValueError, match="flowDirection must be one of"):
        _validate_flow_direction("")


def test_validate_flow_direction_rejects_invalid() -> None:
    """_validate_flow_direction raises ValueError for invalid values."""
    with pytest.raises(ValueError, match="flowDirection must be one of"):
        _validate_flow_direction("SIDEWAYS")
    with pytest.raises(ValueError, match="flowDirection must be one of"):
        _validate_flow_direction("IN")


# --- GET vendors ---


@patch("registry_lambda._get_connection")
@patch("registry_lambda._upsert_vendor")
def test_post_vendor_accepts_non_standard_format(mock_upsert, mock_conn) -> None:
    """POST /v1/registry/vendors accepts vendor codes that are not LH001-style (e.g. ACME)."""
    mock_conn.return_value.__enter__.return_value = None
    mock_upsert.return_value = {
        "id": "u1",
        "vendor_code": "ACME",
        "vendor_name": "Acme Corp",
        "created_at": "2024-01-01",
        "updated_at": None,
    }
    event = {
        "path": "/v1/registry/vendors",
        "rawPath": "/v1/registry/vendors",
        "httpMethod": "POST",
        "headers": {},
        "body": json.dumps({"vendorCode": "ACME", "vendorName": "Acme Corp"}),
        "requestContext": AUTH_REQUEST_CONTEXT,
    }
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["vendor"]["vendor_code"] == "ACME"
    mock_upsert.assert_called_once()
    assert mock_upsert.call_args[0][1] == "ACME"


@patch("registry_lambda._get_connection")
def test_get_vendors_returns_items_next_cursor(mock_conn) -> None:
    """GET /v1/registry/vendors returns items and nextCursor."""
    _mock_cursor(mock_conn, [
        {"id": "a1", "vendor_code": "LH001", "vendor_name": "Vendor A", "is_active": True, "created_at": "2024-01-01", "updated_at": None},
        {"id": "a2", "vendor_code": "LH002", "vendor_name": "Vendor B", "is_active": True, "created_at": "2024-01-02", "updated_at": None},
    ])
    event = {
        "path": "/v1/registry/vendors",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "items" in body
    assert "nextCursor" in body
    assert len(body["items"]) == 2
    assert body["items"][0]["vendorCode"] == "LH001"
    assert body["items"][0]["vendorName"] == "Vendor A"
    assert body["items"][1]["vendorCode"] == "LH002"


# --- GET allowlist ---


def _allowlist_post_event(
    source_vendor: str = "LH001",
    target_vendor: str = "LH002",
    operation_code: str = "GET_WEATHER",
    flow_direction: str | None = None,
) -> dict:
    """Build POST /v1/registry/allowlist event for explicit source/target pair."""
    body: dict = {
        "operationCode": operation_code,
        "sourceVendorCode": source_vendor,
        "targetVendorCode": target_vendor,
    }
    if flow_direction is not None:
        body["flowDirection"] = flow_direction
    return {
        "path": "/v1/registry/allowlist",
        "rawPath": "/v1/registry/allowlist",
        "httpMethod": "POST",
        "headers": {},
        "body": json.dumps(body),
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT_POST,
    }


def test_derive_flow_direction_for_operation() -> None:
    """derive_flow_direction_for_operation maps direction policy to flow_direction."""
    assert derive_flow_direction_for_operation("PROVIDER_RECEIVES_ONLY") == "OUTBOUND"
    assert derive_flow_direction_for_operation("TWO_WAY") == "BOTH"
    assert derive_flow_direction_for_operation(None) == "BOTH"
    assert derive_flow_direction_for_operation("") == "BOTH"
    assert derive_flow_direction_for_operation("unknown") == "BOTH"


@patch("registry_lambda._get_connection")
@patch("registry_lambda._execute_one")
@patch("registry_lambda._upsert_allowlist")
def test_post_allowlist_derives_flow_from_operation_two_way(
    mock_upsert, mock_exec_one, mock_conn
) -> None:
    """
    POST allowlist: for TWO_WAY operations, flow_direction defaults to BOTH
    when client omits it; when client supplies INBOUND/OUTBOUND/BOTH, we accept as-is.
    """
    mock_conn.return_value.__enter__.return_value = object()
    mock_exec_one.side_effect = [
        {"direction_policy": "TWO_WAY"},
        {"direction_policy": "TWO_WAY"},
    ]
    mock_upsert.return_value = {"id": "a1"}
    event = _allowlist_post_event(flow_direction="INBOUND")
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    mock_upsert.assert_called_once()
    call_args = mock_upsert.call_args[0]
    # _upsert_allowlist(conn, source, target, operation_code, flow_direction, ...)
    assert call_args[4] == "INBOUND"


@patch("registry_lambda._get_connection")
@patch("registry_lambda._execute_one")
@patch("registry_lambda._upsert_allowlist")
def test_post_allowlist_derives_flow_from_operation_provider_receives_only(
    mock_upsert, mock_exec_one, mock_conn
) -> None:
    """
    POST allowlist: PROVIDER_RECEIVES_ONLY operation -> flow_direction OUTBOUND
    when client omits flowDirection.
    """
    mock_conn.return_value.__enter__.return_value = object()
    mock_exec_one.side_effect = [
        {"direction_policy": "PROVIDER_RECEIVES_ONLY"},
        {"direction_policy": "PROVIDER_RECEIVES_ONLY"},
    ]
    mock_upsert.return_value = {"id": "a2"}
    event = _allowlist_post_event(source_vendor="LH001", target_vendor="LH002")
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    call_args = mock_upsert.call_args[0]
    # _upsert_allowlist(conn, source, target, operation_code, flow_direction, ...)
    assert call_args[4] == "OUTBOUND"


@patch("registry_lambda._get_connection")
@patch("registry_lambda._execute_one")
def test_post_allowlist_provider_receives_only_rejects_inbound(
    mock_exec_one, mock_conn
) -> None:
    """
    POST allowlist with PROVIDER_RECEIVES_ONLY: INBOUND is rejected with DIRECTION_POLICY_VIOLATION.
    The restriction is on the allowed direction only, not on which vendor is source/target.
    """
    mock_conn.return_value.__enter__.return_value = object()
    mock_exec_one.side_effect = [
        {"direction_policy": "PROVIDER_RECEIVES_ONLY"},
        {"direction_policy": "PROVIDER_RECEIVES_ONLY"},
    ]

    event = _allowlist_post_event(
        source_vendor="ACME",
        target_vendor="LH001",
        flow_direction="INBOUND",
    )
    resp = handler(event, None)
    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "DIRECTION_POLICY_VIOLATION"
    assert "flow_direction must be OUTBOUND" in body.get("error", {}).get("message", "")


@patch("registry_lambda._get_connection")
def test_get_allowlist_returns_items_next_cursor(mock_conn) -> None:
    """GET /v1/registry/allowlist returns items and nextCursor."""
    _mock_cursor(mock_conn, [
        {
            "id": "b1",
            "source_vendor_code": "LH001",
            "target_vendor_code": "LH002",
            "is_any_source": False,
            "is_any_target": False,
            "operation_code": "GET_RECEIPT",
            "rule_scope": "admin",
            "flow_direction": "BOTH",
            "created_at": "2024-01-01",
        },
    ])
    event = {
        "path": "/v1/registry/allowlist",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "items" in body
    assert "nextCursor" in body
    assert len(body["items"]) == 1
    assert body["items"][0]["sourceVendorCode"] == "LH001"
    assert body["items"][0]["targetVendorCode"] == "LH002"
    assert body["items"][0]["operationCode"] == "GET_RECEIPT"


# --- GET endpoints ---


@patch("registry_lambda._get_connection")
def test_get_endpoints_returns_items_next_cursor(mock_conn) -> None:
    """GET /v1/registry/endpoints returns items and nextCursor."""
    _mock_cursor(mock_conn, [
        {"id": "c1", "vendor_code": "LH002", "operation_code": "GET_RECEIPT", "url": "https://example.com", "http_method": "POST", "payload_format": None, "timeout_ms": 30000, "is_active": True, "created_at": "2024-01-01", "updated_at": None},
    ])
    event = {
        "path": "/v1/registry/endpoints",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "items" in body
    assert "nextCursor" in body
    assert len(body["items"]) == 1
    assert body["items"][0]["vendorCode"] == "LH002"
    assert body["items"][0]["operationCode"] == "GET_RECEIPT"
    assert body["items"][0]["url"] == "https://example.com"


# --- GET /v1/registry/readiness ---


@patch("registry_lambda._compute_readiness")
@patch("registry_lambda._get_connection")
def test_get_readiness_single_op_returns_structured_report(mock_conn, mock_compute) -> None:
    """GET /v1/registry/readiness?vendorCode=LH002&operationCode=GET_RECEIPT returns structured report."""
    cur_mock = mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur_mock.fetchone.return_value = {"1": 1}
    cur_mock.fetchall.return_value = []
    mock_compute.return_value = {
        "vendorCode": "LH002",
        "operationCode": "GET_RECEIPT",
        "checks": [
            {"name": "endpoint_configured", "ok": True, "details": {}},
            {"name": "endpoint_verified", "ok": False, "details": {"status": "PENDING"}},
            {"name": "canonical_contract_present", "ok": True},
            {"name": "mappings_present", "ok": False, "details": {"missing": ["TO_CANONICAL_RESPONSE"]}},
        ],
        "overallOk": False,
    }
    event = _readiness_get_event(vendor_code="LH002", operation_code="GET_RECEIPT")
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["vendorCode"] == "LH002"
    assert body["operationCode"] == "GET_RECEIPT"
    assert "checks" in body
    assert len(body["checks"]) == 4
    assert body["checks"][0]["name"] == "endpoint_configured"
    assert body["checks"][0]["ok"] is True
    assert body["checks"][1]["name"] == "endpoint_verified"
    assert body["checks"][1]["details"]["status"] == "PENDING"
    assert body["checks"][3]["details"]["missing"] == ["TO_CANONICAL_RESPONSE"]
    assert body["overallOk"] is False


@patch("registry_lambda._get_vendor_operations_for_readiness")
@patch("registry_lambda._compute_readiness")
@patch("registry_lambda._get_connection")
def test_get_readiness_all_ops_returns_items_array(mock_conn, mock_compute, mock_get_ops) -> None:
    """GET /v1/registry/readiness?vendorCode=LH002 (no operationCode) returns items for each op."""
    cur_mock = mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur_mock.fetchone.return_value = {"1": 1}
    cur_mock.fetchall.return_value = []
    mock_get_ops.return_value = ["GET_RECEIPT", "SEND_RECEIPT"]
    mock_compute.side_effect = [
        {"vendorCode": "LH002", "operationCode": "GET_RECEIPT", "checks": [], "overallOk": True},
        {"vendorCode": "LH002", "operationCode": "SEND_RECEIPT", "checks": [], "overallOk": False},
    ]
    event = _readiness_get_event(vendor_code="LH002", operation_code=None)
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["vendorCode"] == "LH002"
    assert "items" in body
    assert len(body["items"]) == 2
    assert body["items"][0]["operationCode"] == "GET_RECEIPT"
    assert body["items"][1]["operationCode"] == "SEND_RECEIPT"


@patch("registry_lambda._get_connection")
def test_get_readiness_nonexistent_vendor_returns_400(mock_conn) -> None:
    """GET /v1/registry/readiness?vendorCode=NON_EXISTENT returns 400 VALIDATION_ERROR when vendor not found."""
    cur_mock = mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur_mock.fetchone.return_value = None
    cur_mock.fetchall.return_value = []
    event = _readiness_get_event(vendor_code="NON_EXISTENT")
    resp = handler(event, None)
    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "not found" in body["error"]["message"].lower()


@patch("registry_lambda._get_connection")
def test_get_readiness_vendor_exists_no_operations_returns_200_empty_items(mock_conn) -> None:
    """GET /v1/registry/readiness?vendorCode=ACME when vendor exists but has no operations returns 200 with items: []."""
    cur_mock = mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur_mock.fetchone.side_effect = [{"1": 1}]  # vendor exists
    cur_mock.fetchall.return_value = []  # no ops
    event = _readiness_get_event(vendor_code="ACME")
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["vendorCode"] == "ACME"
    assert body["items"] == []


def test_get_readiness_missing_vendor_code_returns_400() -> None:
    """GET /v1/registry/readiness without vendorCode returns 400."""
    event = {
        "path": "/v1/registry/readiness",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }
    resp = handler(event, None)
    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "VALIDATION_ERROR"


# --- POST /v1/registry/readiness/batch ---


def _readiness_batch_event(
    vendor_codes: list[str],
    operation_code: str | None = None,
) -> dict:
    """Build POST /v1/registry/readiness/batch event."""
    body = {"vendorCodes": vendor_codes}
    if operation_code:
        body["operationCode"] = operation_code
    return {
        "path": "/v1/registry/readiness/batch",
        "rawPath": "/v1/registry/readiness/batch",
        "httpMethod": "POST",
        "headers": {},
        "body": json.dumps(body),
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT_POST,
    }


@patch("registry_lambda._compute_readiness")
@patch("registry_lambda._get_connection")
def test_post_readiness_batch_single_op_happy_path(
    mock_conn, mock_compute
) -> None:
    """POST /v1/registry/readiness/batch with 3 vendorCodes + operationCode returns items."""
    mock_compute.side_effect = [
        {"vendorCode": "LH001", "operationCode": "GET_RECEIPT", "checks": [], "overallOk": True},
        {"vendorCode": "LH002", "operationCode": "GET_RECEIPT", "checks": [], "overallOk": False},
        {"vendorCode": "LH003", "operationCode": "GET_RECEIPT", "checks": [], "overallOk": True},
    ]
    event = _readiness_batch_event(["LH001", "LH002", "LH003"], operation_code="GET_RECEIPT")
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "items" in body
    assert len(body["items"]) == 3
    assert body["items"][0]["vendorCode"] == "LH001"
    assert body["items"][0]["operationCode"] == "GET_RECEIPT"
    assert body["items"][0]["overallOk"] is True
    assert body["items"][0]["error"] is None
    assert body["items"][1]["vendorCode"] == "LH002"
    assert body["items"][1]["overallOk"] is False
    assert body["items"][2]["vendorCode"] == "LH003"


@patch("registry_lambda._get_vendor_operations_for_readiness")
@patch("registry_lambda._get_connection")
def test_post_readiness_batch_all_ops_happy_path(
    mock_conn, mock_get_ops
) -> None:
    """POST /v1/registry/readiness/batch without operationCode uses batch path."""
    mock_get_ops.return_value = ["GET_RECEIPT", "SEND_RECEIPT"]
    event = _readiness_batch_event(["LH001"])
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "items" in body
    assert len(body["items"]) == 1
    assert body["items"][0]["vendorCode"] == "LH001"
    assert body["items"][0]["error"] is None
    assert "items" in body["items"][0]
    assert len(body["items"][0]["items"]) == 2


def test_post_readiness_batch_missing_vendor_codes_returns_400() -> None:
    """POST /v1/registry/readiness/batch with empty vendorCodes returns 400."""
    event = _readiness_batch_event([])
    resp = handler(event, None)
    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "VALIDATION_ERROR"


def test_post_readiness_batch_invalid_body_returns_400() -> None:
    """POST /v1/registry/readiness/batch without vendorCodes in body returns 400."""
    event = _readiness_batch_event(["LH001"])
    event["body"] = json.dumps({})
    resp = handler(event, None)
    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "VALIDATION_ERROR"


@patch("registry_lambda._compute_readiness")
@patch("registry_lambda._get_connection")
def test_post_readiness_batch_one_vendor_error_returns_partial(
    mock_conn, mock_compute
) -> None:
    """One vendor raises; others succeed; response returns 200 with error in failed item."""
    def compute_side_effect(conn, vc, op):
        if vc == "LH002":
            raise ValueError("DB error for LH002")
        return {"vendorCode": vc, "operationCode": op, "checks": [], "overallOk": True}

    mock_compute.side_effect = compute_side_effect
    event = _readiness_batch_event(["LH001", "LH002", "LH003"], operation_code="GET_RECEIPT")
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert len(body["items"]) == 3
    assert body["items"][0]["vendorCode"] == "LH001"
    assert body["items"][0]["error"] is None
    assert body["items"][1]["vendorCode"] == "LH002"
    assert "error" in body["items"][1]
    assert body["items"][1]["error"]["code"] == "READINESS_ERROR"
    assert body["items"][2]["vendorCode"] == "LH003"
    assert body["items"][2]["error"] is None


# --- nextCursor when more rows ---


@patch("registry_lambda._get_connection")
def test_get_vendors_returns_next_cursor_when_more_rows(mock_conn) -> None:
    """When limit+1 rows returned, nextCursor is set."""
    # Return 3 rows; with limit=2 we get 2 items and nextCursor
    _mock_cursor(mock_conn, [
        {"id": "1", "vendor_code": "A", "vendor_name": "A", "is_active": True, "created_at": "2024-01-03", "updated_at": None},
        {"id": "2", "vendor_code": "B", "vendor_name": "B", "is_active": True, "created_at": "2024-01-02", "updated_at": None},
        {"id": "3", "vendor_code": "C", "vendor_name": "C", "is_active": True, "created_at": "2024-01-01", "updated_at": None},
    ])
    event = {
        "path": "/v1/registry/vendors",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {"limit": "2"},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert len(body["items"]) == 2
    assert body["nextCursor"] is not None
    assert body["items"][0]["vendorCode"] == "A"
    assert body["items"][1]["vendorCode"] == "B"


# --- Empty DB (null-safe, no 500s) ---


@patch("registry_lambda._get_connection")
def test_get_vendors_empty_db_returns_200_with_empty_list(mock_conn) -> None:
    """GET /v1/registry/vendors with no vendors returns 200 and empty items."""
    _mock_cursor(mock_conn, [])
    event = {
        "path": "/v1/registry/vendors",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {"limit": "200"},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["items"] == []
    assert body.get("nextCursor") is None


@patch("registry_lambda._get_connection")
def test_get_allowlist_empty_db_returns_200_with_empty_list(mock_conn) -> None:
    """GET /v1/registry/allowlist with no rows returns 200 and empty items."""
    _mock_cursor(mock_conn, [])
    event = {
        "path": "/v1/registry/allowlist",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["items"] == []
    assert body.get("nextCursor") is None


@patch("registry_lambda._get_connection")
def test_get_operations_empty_db_returns_200_with_empty_list(mock_conn) -> None:
    """GET /v1/registry/operations with no operations returns 200 and empty items."""
    _mock_cursor(mock_conn, [])
    event = {
        "path": "/v1/registry/operations",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["items"] == []


@patch("registry_lambda._get_connection")
def test_get_endpoints_empty_db_returns_200_with_empty_list(mock_conn) -> None:
    """GET /v1/registry/endpoints with no endpoints returns 200 and empty items."""
    _mock_cursor(mock_conn, [])
    event = {
        "path": "/v1/registry/endpoints",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["items"] == []
    assert body.get("nextCursor") is None


@patch("registry_lambda._get_connection")
def test_get_operations_with_allowlist_filter_empty_returns_200(mock_conn) -> None:
    """GET /v1/registry/operations?sourceVendorCode=X&targetVendorCode=Y with no matching allowlist returns 200 and empty items."""
    _mock_cursor(mock_conn, [])
    event = {
        "path": "/v1/registry/operations",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {"sourceVendorCode": "LH001", "targetVendorCode": "LH002"},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["items"] == []


@patch("registry_lambda._get_connection")
def test_get_operations_with_allowlist_filter_two_vendors_returns_ops(mock_conn) -> None:
    """Admin LH001->LH002: operations filtered by allowlist returns GET_RECEIPT."""
    _mock_cursor(mock_conn, [
        {
            "id": "op1",
            "operation_code": "GET_RECEIPT",
            "description": "Get receipt",
            "canonical_version": "v1",
            "is_async_capable": True,
            "is_active": True,
            "created_at": "2024-01-01",
            "updated_at": None,
        },
    ])
    event = {
        "path": "/v1/registry/operations",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {"sourceVendorCode": "LH001", "targetVendorCode": "LH002"},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert len(body["items"]) == 1
    assert body["items"][0]["operationCode"] == "GET_RECEIPT"


def _feature_gates_get_event() -> dict:
    """Build GET /v1/registry/feature-gates event."""
    return {
        "path": "/v1/registry/feature-gates",
        "rawPath": "/v1/registry/feature-gates",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": None,
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _feature_gates_put_event(gate_key: str, enabled: bool) -> dict:
    """Build PUT /v1/registry/feature-gates/{gateKey} event."""
    return {
        "path": f"/v1/registry/feature-gates/{gate_key}",
        "rawPath": f"/v1/registry/feature-gates/{gate_key}",
        "httpMethod": "PUT",
        "headers": {},
        "body": json.dumps({"enabled": enabled}),
        "pathParameters": {"gateKey": gate_key},
        "requestContext": {"http": {"method": "PUT"}, "authorizer": JWT_AUTHORIZER},
    }


@patch("registry_lambda._get_connection")
def test_get_feature_gates_returns_items(mock_conn) -> None:
    """GET /v1/registry/feature-gates returns seeded gates."""
    from datetime import datetime, timezone
    ts = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)
    rows = [
        {"feature_code": "GATE_ALLOWLIST_RULE", "vendor_code": None, "is_enabled": True, "updated_at": ts},
        {"feature_code": "GATE_ENDPOINT_CONFIG", "vendor_code": None, "is_enabled": False, "updated_at": ts},
    ]
    _mock_cursor(mock_conn, rows)
    event = _feature_gates_get_event()
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    items = body.get("items", [])
    assert len(items) == 2
    by_key = {g["gateKey"]: g for g in items}
    assert by_key["GATE_ALLOWLIST_RULE"]["enabled"] is True
    assert by_key["GATE_ENDPOINT_CONFIG"]["enabled"] is False


@patch("registry_lambda._get_connection")
def test_put_feature_gate_updates_enabled(mock_conn) -> None:
    """PUT /v1/registry/feature-gates/{gateKey} updates enabled and persists."""
    from datetime import datetime, timezone
    cursor_mock = mock_conn.return_value.__enter__.return_value.cursor.return_value
    cursor_mock.__enter__.return_value = cursor_mock
    cursor_mock.__exit__.return_value = False
    cursor_mock.fetchone.return_value = {
        "feature_code": "GATE_MAPPING_CONFIG",
        "vendor_code": None,
        "is_enabled": False,
        "updated_at": datetime(2026, 2, 25, 13, 0, 0, tzinfo=timezone.utc),
    }
    event = _feature_gates_put_event("GATE_MAPPING_CONFIG", False)
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["gateKey"] == "GATE_MAPPING_CONFIG"
    assert body["enabled"] is False


def _auth_profiles_test_connection_event(body: dict) -> dict:
    return {
        "path": "/v1/registry/auth-profiles/test-connection",
        "rawPath": "/v1/registry/auth-profiles/test-connection",
        "httpMethod": "POST",
        "headers": {},
        "body": json.dumps(body),
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT_POST,
    }


def _auth_profiles_token_preview_event(body: dict) -> dict:
    return {
        "path": "/v1/registry/auth-profiles/token-preview",
        "rawPath": "/v1/registry/auth-profiles/token-preview",
        "httpMethod": "POST",
        "headers": {},
        "body": json.dumps(body),
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT_POST,
    }


def _auth_profiles_mtls_validate_event(body: dict) -> dict:
    return {
        "path": "/v1/registry/auth-profiles/mtls-validate",
        "rawPath": "/v1/registry/auth-profiles/mtls-validate",
        "httpMethod": "POST",
        "headers": {},
        "body": json.dumps(body),
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT_POST,
    }


@patch("registry_lambda.socket.getaddrinfo")
def test_auth_profile_test_connection_blocks_ssrf(mock_getaddrinfo) -> None:
    mock_getaddrinfo.return_value = [(None, None, None, None, ("169.254.169.254", 443))]
    event = _auth_profiles_test_connection_event(
        {
            "authType": "API_KEY_HEADER",
            "authConfig": {"headerName": "Api-Key", "key": "secret-value"},
            "url": "http://169.254.169.254/latest/meta-data",
            "method": "GET",
            "timeoutMs": 5000,
        }
    )
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["ok"] is False
    assert body["error"]["category"] == "BLOCKED"


@patch("registry_lambda.requests.request")
@patch("registry_lambda.socket.getaddrinfo")
def test_auth_profile_test_connection_redacts_secrets(mock_getaddrinfo, mock_request) -> None:
    class _Resp:
        status_code = 200
        text = "ok"

    mock_getaddrinfo.return_value = [(None, None, None, None, ("8.8.8.8", 443))]
    mock_request.return_value = _Resp()
    event = _auth_profiles_test_connection_event(
        {
            "authType": "BEARER",
            "authConfig": {"token": "very-secret-token"},
            "url": "https://example.com/health",
            "method": "GET",
        }
    )
    resp = handler(event, None)
    body = json.loads(resp["body"])
    assert body["ok"] is True
    auth_dbg = body["debug"]["resolvedAuth"]["appliedHeaders"]
    assert auth_dbg["Authorization"] == "Bearer ***REDACTED***"
    assert "very-secret-token" not in json.dumps(body)


@patch("registry_lambda.requests.request", side_effect=requests.Timeout("timeout"))
@patch("registry_lambda.socket.getaddrinfo")
def test_auth_profile_test_connection_timeout_enforced(mock_getaddrinfo, _mock_request) -> None:
    mock_getaddrinfo.return_value = [(None, None, None, None, ("8.8.8.8", 443))]
    event = _auth_profiles_test_connection_event(
        {
            "authType": "API_KEY_QUERY",
            "authConfig": {"paramName": "api_key", "key": "secret"},
            "url": "https://example.com/health",
            "method": "GET",
            "timeoutMs": 20000,
        }
    )
    resp = handler(event, None)
    body = json.loads(resp["body"])
    assert body["ok"] is False
    assert body["error"]["category"] == "TIMEOUT"


@patch("registry_lambda.requests.post")
def test_token_preview_redacts_token(mock_post) -> None:
    class _Resp:
        status_code = 200

        def json(self):
            return {"access_token": "abcdefghijklmnopqrstuvwx.yyy.zzzzzz", "expires_in": 3600}

    mock_post.return_value = _Resp()
    event = _auth_profiles_token_preview_event(
        {
            "authType": "JWT_BEARER_TOKEN",
            "authConfig": {
                "tokenUrl": "https://idp.example.com/token",
                "clientId": "client",
                "clientSecret": "secret",
                "scope": "read",
            },
        }
    )
    resp = handler(event, None)
    body = json.loads(resp["body"])
    assert body["ok"] is True
    assert body["tokenRedacted"] is not None
    assert "secret" not in json.dumps(body)


@patch("registry_lambda.requests.post")
def test_token_preview_jwt_claim_extraction(mock_post) -> None:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(
        json.dumps({"iss": "issuer", "aud": "audience", "exp": 123, "iat": 100}).encode()
    ).decode().rstrip("=")
    token = f"{header}.{payload}.sig"

    class _Resp:
        status_code = 200

        def json(self):
            return {"access_token": token, "expires_in": 3600}

    mock_post.return_value = _Resp()
    event = _auth_profiles_token_preview_event(
        {
            "authType": "JWT_BEARER_TOKEN",
            "authConfig": {
                "tokenUrl": "https://idp.example.com/token",
                "clientId": "client",
                "clientSecret": "secret",
            },
        }
    )
    resp = handler(event, None)
    body = json.loads(resp["body"])
    assert body["ok"] is True
    assert body["jwtClaims"]["iss"] == "issuer"
    assert body["jwtClaims"]["aud"] == "audience"


@patch("registry_lambda.requests.post")
def test_token_preview_non_jwt_claims_null(mock_post) -> None:
    class _Resp:
        status_code = 200

        def json(self):
            return {"access_token": "opaque_access_token", "expires_in": 3600}

    mock_post.return_value = _Resp()
    event = _auth_profiles_token_preview_event(
        {
            "authType": "JWT_BEARER_TOKEN",
            "authConfig": {
                "tokenUrl": "https://idp.example.com/token",
                    "clientId": "client-non-jwt",
                "clientSecret": "secret",
            },
        }
    )
    resp = handler(event, None)
    body = json.loads(resp["body"])
    assert body["ok"] is True
    assert body["jwtClaims"] is None


def test_mtls_validate_parse_failures_safe() -> None:
    pytest.importorskip("cryptography")
    event = _auth_profiles_mtls_validate_event(
        {
            "certificatePem": "invalid",
            "privateKeyPem": "invalid",
        }
    )
    resp = handler(event, None)
    body = json.loads(resp["body"])
    assert body["ok"] is False
    assert body["error"]["category"] == "PARSE"


def test_mtls_validate_mismatched_key_returns_invalid() -> None:
    pytest.importorskip("cryptography")
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from datetime import datetime, timedelta, timezone

    key1 = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key2 = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "example.com")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key1.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=30))
        .sign(key1, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    wrong_key_pem = key2.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    event = _auth_profiles_mtls_validate_event(
        {"certificatePem": cert_pem, "privateKeyPem": wrong_key_pem}
    )
    resp = handler(event, None)
    body = json.loads(resp["body"])
    assert body["ok"] is False
    assert body["error"]["category"] == "MISMATCH"


def test_mtls_validate_expired_cert_returns_invalid() -> None:
    pytest.importorskip("cryptography")
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from datetime import datetime, timedelta, timezone

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "expired.example.com")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=10))
        .not_valid_after(datetime.now(timezone.utc) - timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    event = _auth_profiles_mtls_validate_event(
        {"certificatePem": cert_pem, "privateKeyPem": key_pem}
    )
    resp = handler(event, None)
    body = json.loads(resp["body"])
    assert body["ok"] is False
    assert "EXPIRED" in body.get("warnings", [])
