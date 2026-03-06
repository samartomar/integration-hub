"""Tests for Sandbox backend endpoints."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from registry_lambda import handler  # noqa: E402

JWT_AUTHORIZER = {
    "principalId": "okta|test",
    "jwt": {"claims": {"sub": "okta|test", "aud": "api://default", "groups": ["admins", "admin"]}},
}
AUTH_REQUEST_CONTEXT = {"http": {"method": "GET"}, "authorizer": JWT_AUTHORIZER}


def _sandbox_operations_list_event() -> dict:
    """Build GET /v1/sandbox/canonical/operations event."""
    return {
        "path": "/v1/sandbox/canonical/operations",
        "rawPath": "/v1/sandbox/canonical/operations",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _sandbox_operation_detail_event(operation_code: str, version: str | None = None) -> dict:
    """Build GET /v1/sandbox/canonical/operations/{operationCode} event."""
    qp = {"version": version} if version else {}
    return {
        "path": f"/v1/sandbox/canonical/operations/{operation_code}",
        "rawPath": f"/v1/sandbox/canonical/operations/{operation_code}",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": qp,
        "pathParameters": {"operationCode": operation_code},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _sandbox_request_validate_event(body: dict) -> dict:
    """Build POST /v1/sandbox/request/validate event."""
    return {
        "path": "/v1/sandbox/request/validate",
        "rawPath": "/v1/sandbox/request/validate",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _sandbox_mock_run_event(body: dict) -> dict:
    """Build POST /v1/sandbox/mock/run event."""
    return {
        "path": "/v1/sandbox/mock/run",
        "rawPath": "/v1/sandbox/mock/run",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_sandbox_operations_list_returns_both_ops(_mock_auth: object) -> None:
    """GET /v1/sandbox/canonical/operations returns both operations."""
    event = _sandbox_operations_list_event()
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    ops = {item["operationCode"]: item for item in body["items"]}
    assert "GET_VERIFY_MEMBER_ELIGIBILITY" in ops
    assert "GET_MEMBER_ACCUMULATORS" in ops


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_sandbox_operation_detail_returns_detail(_mock_auth: object) -> None:
    """GET /v1/sandbox/canonical/operations/{operationCode} returns operation details."""
    event = _sandbox_operation_detail_event("GET_VERIFY_MEMBER_ELIGIBILITY")
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert body["version"] == "1.0"
    assert "requestPayloadSchema" in body
    assert "examples" in body


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_sandbox_operation_detail_version_v1_resolves(_mock_auth: object) -> None:
    """GET with ?version=v1 resolves to 1.0."""
    event = _sandbox_operation_detail_event("GET_VERIFY_MEMBER_ELIGIBILITY")
    event["queryStringParameters"] = {"version": "v1"}
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["version"] == "1.0"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_sandbox_request_validate_success(_mock_auth: object) -> None:
    """POST /v1/sandbox/request/validate success case."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "payload": {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"},
    }
    event = _sandbox_request_validate_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    data = json.loads(result["body"])
    assert data["valid"] is True
    assert data.get("normalizedVersion") == "1.0"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_sandbox_request_validate_invalid(_mock_auth: object) -> None:
    """POST /v1/sandbox/request/validate invalid case."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "payload": {"memberIdWithPrefix": "X", "date": "bad-date"},
    }
    event = _sandbox_request_validate_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    data = json.loads(result["body"])
    assert data["valid"] is False
    assert "errors" in data
    assert len(data["errors"]) > 0


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_sandbox_mock_run_success(_mock_auth: object) -> None:
    """POST /v1/sandbox/mock/run success case."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "payload": {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"},
    }
    event = _sandbox_mock_run_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    data = json.loads(result["body"])
    assert data["valid"] is True
    assert data["mode"] == "MOCK"
    assert "requestEnvelope" in data
    assert "responseEnvelope" in data
    assert "notes" in data


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_sandbox_mock_run_invalid(_mock_auth: object) -> None:
    """POST /v1/sandbox/mock/run invalid case."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "payload": {"memberIdWithPrefix": "X", "date": "invalid"},
    }
    event = _sandbox_mock_run_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    data = json.loads(result["body"])
    assert data["valid"] is False
    assert "errors" in data


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_sandbox_operation_not_found_returns_404(_mock_auth: object) -> None:
    """GET /v1/sandbox/canonical/operations/{operationCode} returns 404 for unknown operation."""
    event = _sandbox_operation_detail_event("UNKNOWN_OPERATION_XYZ")
    result = handler(event, None)
    assert result["statusCode"] == 404
    body = json.loads(result["body"])
    assert "error" in body
    assert body["error"]["code"] == "NOT_FOUND"
