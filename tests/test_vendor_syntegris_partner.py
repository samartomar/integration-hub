"""Unit tests for Vendor Registry Lambda - Syntegris partner endpoints (schema-backed, vendor-scoped)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from vendor_registry_lambda import handler  # noqa: E402
from vendor_registry_jwt import add_jwt_auth  # noqa: E402


def _event(path: str, method: str = "GET", body: dict | None = None, query: dict | None = None) -> dict:
    ev = {
        "path": path,
        "rawPath": path,
        "httpMethod": method,
        "pathParameters": {},
        "queryStringParameters": query or {},
        "requestContext": {"http": {"method": method}, "requestId": "test-req-id"},
        "headers": {},
    }
    if body is not None:
        ev["body"] = json.dumps(body) if isinstance(body, dict) else body
    return ev


def _mock_conn() -> MagicMock:
    """Mock DB connection for vendor validation (fetchone returns vendor active)."""
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = (1,)
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = None
    conn.commit = MagicMock()
    conn.rollback = MagicMock()
    return conn


@patch("vendor_registry_lambda._get_connection")
def test_syntegris_canonical_operations_list(mock_conn: MagicMock) -> None:
    """GET /v1/vendor/syntegris/canonical/operations - schema-backed list."""
    conn = _mock_conn()
    mock_conn.return_value.__enter__.return_value = conn
    mock_conn.return_value.__exit__.return_value = None

    event = _event("/v1/vendor/syntegris/canonical/operations", "GET")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "transactionId" in body
    assert "items" in body
    assert isinstance(body["items"], list)
    # Schema registry has eligibility and member_accumulators
    op_codes = [o.get("operationCode") for o in body["items"]]
    assert "GET_VERIFY_MEMBER_ELIGIBILITY" in op_codes or len(body["items"]) >= 1


@patch("vendor_registry_lambda._get_connection")
def test_syntegris_canonical_operation_detail(mock_conn: MagicMock) -> None:
    """GET /v1/vendor/syntegris/canonical/operations/{operationCode} - schema-backed detail."""
    conn = _mock_conn()
    mock_conn.return_value.__enter__.return_value = conn
    mock_conn.return_value.__exit__.return_value = None

    event = _event("/v1/vendor/syntegris/canonical/operations/GET_VERIFY_MEMBER_ELIGIBILITY", "GET")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body.get("operationCode") == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert "requestPayloadSchema" in body
    assert "responsePayloadSchema" in body
    assert "examples" in body


@patch("vendor_registry_lambda._get_connection")
def test_syntegris_canonical_operation_detail_not_found(mock_conn: MagicMock) -> None:
    """GET /v1/vendor/syntegris/canonical/operations/UNKNOWN_OP - 404."""
    conn = _mock_conn()
    mock_conn.return_value.__enter__.return_value = conn
    mock_conn.return_value.__exit__.return_value = None

    event = _event("/v1/vendor/syntegris/canonical/operations/UNKNOWN_OP_XYZ", "GET")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 404
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "NOT_FOUND"


@patch("vendor_registry_lambda._get_connection")
def test_syntegris_sandbox_validate(mock_conn: MagicMock) -> None:
    """POST /v1/vendor/syntegris/sandbox/request/validate - valid request."""
    conn = _mock_conn()
    mock_conn.return_value.__enter__.return_value = conn
    mock_conn.return_value.__exit__.return_value = None

    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "payload": {"memberIdWithPrefix": "LH001-M001", "date": "2024-01-15"},
    }
    event = _event("/v1/vendor/syntegris/sandbox/request/validate", "POST", body)
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    data = json.loads(resp["body"])
    assert data.get("valid") is True
    assert "errors" not in data or data["errors"] == []


@patch("vendor_registry_lambda._get_connection")
def test_syntegris_sandbox_mock_run(mock_conn: MagicMock) -> None:
    """POST /v1/vendor/syntegris/sandbox/mock/run - mock sandbox execution."""
    conn = _mock_conn()
    mock_conn.return_value.__enter__.return_value = conn
    mock_conn.return_value.__exit__.return_value = None

    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "payload": {"memberIdWithPrefix": "LH001-M001", "date": "2024-01-15"},
    }
    event = _event("/v1/vendor/syntegris/sandbox/mock/run", "POST", body)
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    data = json.loads(resp["body"])
    assert "operationCode" in data
    assert data.get("mode") == "MOCK"
    assert "requestEnvelope" in data or "errors" in data


@patch("vendor_registry_lambda._get_connection")
def test_syntegris_ai_debug_request_analyze(mock_conn: MagicMock) -> None:
    """POST /v1/vendor/syntegris/ai/debug/request/analyze."""
    conn = _mock_conn()
    mock_conn.return_value.__enter__.return_value = conn
    mock_conn.return_value.__exit__.return_value = None

    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "payload": {"memberId": "M001", "dateOfService": "2024-01-15"},
        "version": "1.0",
    }
    event = _event("/v1/vendor/syntegris/ai/debug/request/analyze", "POST", body)
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    data = json.loads(resp["body"])
    assert "status" in data
    assert "findings" in data or "summary" in data


@patch("vendor_registry_lambda._get_connection")
def test_syntegris_ai_debug_flow_draft_analyze(mock_conn: MagicMock) -> None:
    """POST /v1/vendor/syntegris/ai/debug/flow-draft/analyze."""
    conn = _mock_conn()
    mock_conn.return_value.__enter__.return_value = conn
    mock_conn.return_value.__exit__.return_value = None

    body = {
        "draft": {
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
            "payload": {"memberId": "M001", "dateOfService": "2024-01-15"},
        }
    }
    event = _event("/v1/vendor/syntegris/ai/debug/flow-draft/analyze", "POST", body)
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    data = json.loads(resp["body"])
    assert "status" in data


@patch("vendor_registry_lambda._get_connection")
def test_syntegris_ai_debug_sandbox_result_analyze(mock_conn: MagicMock) -> None:
    """POST /v1/vendor/syntegris/ai/debug/sandbox-result/analyze."""
    conn = _mock_conn()
    mock_conn.return_value.__enter__.return_value = conn
    mock_conn.return_value.__exit__.return_value = None

    body = {
        "result": {
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
            "mode": "MOCK",
            "valid": True,
        }
    }
    event = _event("/v1/vendor/syntegris/ai/debug/sandbox-result/analyze", "POST", body)
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    data = json.loads(resp["body"])
    assert "status" in data


@patch("vendor_registry_lambda._get_connection")
def test_syntegris_runtime_preflight_source_from_auth(mock_conn: MagicMock) -> None:
    """POST /v1/vendor/syntegris/runtime/canonical/preflight - sourceVendor from JWT."""
    conn = _mock_conn()
    mock_conn.return_value.__enter__.return_value = conn
    mock_conn.return_value.__exit__.return_value = None

    body = {
        "targetVendor": "LH002",
        "envelope": {
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
            "direction": "REQUEST",
            "payload": {"memberId": "M001", "dateOfService": "2024-01-15"},
        },
    }
    event = _event("/v1/vendor/syntegris/runtime/canonical/preflight", "POST", body)
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    data = json.loads(resp["body"])
    assert data.get("sourceVendor") == "LH001"
    assert data.get("targetVendor") == "LH002"
    assert "checks" in data
    assert "valid" in data


@patch("vendor_registry_lambda._get_connection")
def test_syntegris_runtime_preflight_vendor_spoof_blocked(mock_conn: MagicMock) -> None:
    """POST preflight with body sourceVendor != auth -> VENDOR_SPOOF_BLOCKED."""
    conn = _mock_conn()
    mock_conn.return_value.__enter__.return_value = conn
    mock_conn.return_value.__exit__.return_value = None

    body = {
        "sourceVendor": "OTHER_VENDOR",
        "targetVendor": "LH002",
        "envelope": {
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
            "direction": "REQUEST",
            "payload": {"memberId": "M001", "dateOfService": "2024-01-15"},
        },
    }
    event = _event("/v1/vendor/syntegris/runtime/canonical/preflight", "POST", body)
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 403
    data = json.loads(resp["body"])
    assert data.get("error", {}).get("code") == "VENDOR_SPOOF_BLOCKED"


@patch("vendor_registry_lambda._get_connection")
def test_syntegris_runtime_preflight_malformed_json(mock_conn: MagicMock) -> None:
    """POST preflight with malformed JSON body -> 400 INVALID_JSON."""
    conn = _mock_conn()
    mock_conn.return_value.__enter__.return_value = conn
    mock_conn.return_value.__exit__.return_value = None

    event = _event("/v1/vendor/syntegris/runtime/canonical/preflight", "POST", body="{ invalid }")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 400
    data = json.loads(resp["body"])
    assert data.get("error", {}).get("code") == "INVALID_JSON"


@patch("vendor_registry_lambda._get_connection")
def test_syntegris_runtime_execute_dry_run(mock_conn: MagicMock) -> None:
    """POST /v1/vendor/syntegris/runtime/canonical/execute - DRY_RUN mode."""
    conn = _mock_conn()
    mock_conn.return_value.__enter__.return_value = conn
    mock_conn.return_value.__exit__.return_value = None

    body = {
        "mode": "DRY_RUN",
        "targetVendor": "LH002",
        "envelope": {
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
            "direction": "REQUEST",
            "payload": {"memberId": "M001", "dateOfService": "2024-01-15"},
        },
    }
    event = _event("/v1/vendor/syntegris/runtime/canonical/execute", "POST", body)
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    data = json.loads(resp["body"])
    assert data.get("mode") == "DRY_RUN"
    assert data.get("sourceVendor") == "LH001"
    assert "preflight" in data
    assert "executeRequestPreview" in data


@patch("vendor_registry_lambda._get_connection")
def test_syntegris_runtime_execute_vendor_spoof_blocked(mock_conn: MagicMock) -> None:
    """POST execute with body sourceVendor != auth -> VENDOR_SPOOF_BLOCKED."""
    conn = _mock_conn()
    mock_conn.return_value.__enter__.return_value = conn
    mock_conn.return_value.__exit__.return_value = None

    body = {
        "mode": "DRY_RUN",
        "sourceVendor": "OTHER_VENDOR",
        "targetVendor": "LH002",
        "envelope": {
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
            "direction": "REQUEST",
            "payload": {"memberId": "M001", "dateOfService": "2024-01-15"},
        },
    }
    event = _event("/v1/vendor/syntegris/runtime/canonical/execute", "POST", body)
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 403
    data = json.loads(resp["body"])
    assert data.get("error", {}).get("code") == "VENDOR_SPOOF_BLOCKED"


@patch("vendor_registry_lambda._get_connection")
def test_syntegris_runtime_execute_malformed_json(mock_conn: MagicMock) -> None:
    """POST execute with malformed JSON -> 400 INVALID_JSON."""
    conn = _mock_conn()
    mock_conn.return_value.__enter__.return_value = conn
    mock_conn.return_value.__exit__.return_value = None

    event = _event("/v1/vendor/syntegris/runtime/canonical/execute", "POST", body="not json")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 400
    data = json.loads(resp["body"])
    assert data.get("error", {}).get("code") == "INVALID_JSON"
