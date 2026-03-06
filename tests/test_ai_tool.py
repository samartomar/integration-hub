"""Unit tests for AI Tool Lambda - schema validation and execute flow."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambdas" / "ai_tool"))


# Set env before importing handler (config reads it)
import os

os.environ.setdefault("VENDOR_API_URL", "https://api.example.com/prod")
os.environ.setdefault("ADMIN_API_URL", "https://admin.example.com")

from handler import handler  # noqa: E402

GET_RECEIPT_SCHEMA = {
    "type": "object",
    "required": ["transactionId"],
    "properties": {"transactionId": {"type": "string", "minLength": 1}},
}


def _input_body(
    source_vendor: str = "LH001",
    target_vendor: str = "LH002",
    operation: str = "GET_RECEIPT",
    operation_code: str | None = None,
    canonical_version: str = "v1",
    parameters: dict | None = None,
    idempotency_key: str | None = None,
) -> dict:
    body: dict = {
        "sourceVendor": source_vendor,
        "targetVendor": target_vendor,
        "operation": operation,
        "canonicalVersion": canonical_version,
        "parameters": parameters or {},
    }
    if operation_code is not None:
        body["operationCode"] = operation_code
    if idempotency_key is not None:
        body["idempotencyKey"] = idempotency_key
    return body


def _event(body: dict | None = None) -> dict:
    payload = body if body is not None else _input_body()
    return {"body": json.dumps(payload)}


def test_missing_source_vendor_returns_needs_input() -> None:
    """Missing sourceVendor returns NEEDS_INPUT with missingFields, no execute call."""
    event = _event({"targetVendor": "LH002", "operation": "GET_RECEIPT", "parameters": {}})
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["status"] == "NEEDS_INPUT"
    assert "sourceVendor" in (body.get("missingFields") or body.get("required") or [])


@patch("handler.call_integration_api")
@patch("handler.get_operation_canonical_version")
@patch("handler.fetch_request_schema")
@patch("handler.validate_allowlist")
@patch("handler.validate_operation_exists_and_active")
@patch("handler.validate_vendor_exists_and_active")
def test_missing_required_parameter_returns_needs_input(
    mock_validate_vendor,
    mock_validate_op,
    mock_validate_allowlist,
    mock_fetch_request_schema,
    mock_get_canonical,
    mock_call_execute,
) -> None:
    """Missing required parameter causes NEEDS_INPUT, does not call /execute."""
    mock_get_canonical.return_value = "v1"
    mock_fetch_request_schema.return_value = GET_RECEIPT_SCHEMA

    event = _event(_input_body(parameters={}))  # missing transactionId
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["status"] == "NEEDS_INPUT"
    assert body["message"] == "Missing or invalid parameters"
    assert len(body["violations"]) >= 1
    assert any("transactionId" in v.get("message", "") for v in body["violations"])
    assert body.get("required") == ["transactionId"] or (
        body.get("violations") and any("transactionId" in str(v.get("message", "")) for v in body["violations"])
    )
    mock_call_execute.assert_not_called()


@patch("handler.call_integration_api")
@patch("handler.get_operation_canonical_version")
@patch("handler.fetch_request_schema")
@patch("handler.validate_allowlist")
@patch("handler.validate_operation_exists_and_active")
@patch("handler.validate_vendor_exists_and_active")
def test_valid_request_calls_execute(
    mock_validate_vendor,
    mock_validate_op,
    mock_validate_allowlist,
    mock_fetch_request_schema,
    mock_get_canonical,
    mock_call_execute,
) -> None:
    """Valid parameters satisfy schema; /execute is called and response returned."""
    mock_get_canonical.return_value = "v1"
    mock_fetch_request_schema.return_value = GET_RECEIPT_SCHEMA
    mock_call_execute.return_value = {
        "transactionId": "tx-123",
        "correlationId": "corr-456",
        "responseBody": {"status": "completed", "downstream": {}},
    }

    event = _event(_input_body(parameters={"transactionId": "tx-abc"}))
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["status"] == "OK"
    assert body["executeResult"]["transactionId"] == "tx-123"
    assert body["executeResult"]["correlationId"] == "corr-456"
    assert body["executeResult"]["responseBody"]["status"] == "completed"
    mock_call_execute.assert_called_once()


@patch("handler.get_operation_canonical_version")
@patch("handler.fetch_request_schema")
@patch("handler.validate_allowlist")
@patch("handler.validate_operation_exists_and_active")
@patch("handler.validate_vendor_exists_and_active")
def test_unknown_operation_returns_error(
    mock_validate_vendor,
    mock_validate_op,
    mock_validate_allowlist,
    mock_fetch_request_schema,
    mock_get_canonical,
) -> None:
    """No active contract returns UNKNOWN_OPERATION."""
    mock_get_canonical.return_value = "v1"
    mock_fetch_request_schema.return_value = None

    event = _event(_input_body(parameters={"transactionId": "tx-1"}))
    resp = handler(event, None)

    assert resp["statusCode"] == 404
    body = json.loads(resp["body"])
    assert body["status"] == "ERROR"
    assert body["error"]["code"] == "UNKNOWN_OPERATION"
    assert "GET_RECEIPT" in body["error"]["message"]


@patch("handler.fetch_operations")
def test_list_operations_returns_operations_list(mock_fetch_ops) -> None:
    """ListOperations (no operation) calls fetch_operations and returns list."""
    mock_fetch_ops.return_value = [
        {"operation_code": "GET_RECEIPT", "description": "Get receipt", "canonical_version": "v1"},
    ]
    event = {"body": json.dumps({})}  # No operation -> ListOperations
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["status"] == "OK"
    assert "executeResult" in body
    assert "operations" in body["executeResult"]
    assert len(body["executeResult"]["operations"]) == 1
    assert body["executeResult"]["operations"][0]["operation_code"] == "GET_RECEIPT"
    mock_fetch_ops.assert_called_once_with(is_active=True, source_vendor=None, target_vendor=None)


@patch("handler.call_integration_api")
@patch("handler.get_operation_canonical_version")
@patch("handler.fetch_request_schema")
@patch("handler.validate_allowlist")
@patch("handler.validate_operation_exists_and_active")
@patch("handler.validate_vendor_exists_and_active")
def test_http_error_surfaces_api_error_code_and_message(
    mock_validate_vendor,
    mock_validate_op,
    mock_validate_allowlist,
    mock_fetch_request_schema,
    mock_get_canonical,
    mock_call_execute,
) -> None:
    """HTTPError from API: surfaces error.code and error.message, never invents remediation."""
    from io import BytesIO

    import urllib.error

    mock_get_canonical.return_value = "v1"
    mock_fetch_request_schema.return_value = GET_RECEIPT_SCHEMA
    api_error_body = json.dumps({
        "error": {
            "code": "SCHEMA_VALIDATION_FAILED",
            "message": "Target schema validation failed",
            "violations": ["Missing field x"],
            "details": {"stage": "TARGET_REQUEST"},
        },
    })
    err = urllib.error.HTTPError(
        "https://api.example.com/execute",
        400,
        "Bad Request",
        {},
        BytesIO(api_error_body.encode()),
    )

    mock_call_execute.side_effect = err

    event = _event(_input_body(parameters={"transactionId": "tx-1"}))
    resp = handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body["status"] == "ERROR"
    assert body["error"]["code"] == "SCHEMA_VALIDATION_FAILED"
    assert body["error"]["message"] == "Target schema validation failed"
    assert body["error"]["violations"] == ["Missing field x"]


@patch("handler.fetch_operations")
def test_list_operations_with_vendor_filter(mock_fetch_ops) -> None:
    """ListOperations with sourceVendor and targetVendor filters by allowlist."""
    mock_fetch_ops.return_value = [{"operation_code": "GET_RECEIPT", "description": "Get", "canonical_version": "v1"}]
    event = {"body": json.dumps({"sourceVendor": "LH001", "targetVendor": "LH002"})}
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["status"] == "OK"
    mock_fetch_ops.assert_called_once_with(is_active=True, source_vendor="LH001", target_vendor="LH002")
