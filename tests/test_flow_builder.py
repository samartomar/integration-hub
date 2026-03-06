"""Tests for Flow Builder backend endpoints and draft validation."""

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


def _flow_operations_list_event() -> dict:
    """Build GET /v1/flow/canonical/operations event."""
    return {
        "path": "/v1/flow/canonical/operations",
        "rawPath": "/v1/flow/canonical/operations",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _flow_operation_detail_event(operation_code: str, version: str | None = None) -> dict:
    """Build GET /v1/flow/canonical/operations/{operationCode} event."""
    qp = {"version": version} if version else {}
    return {
        "path": f"/v1/flow/canonical/operations/{operation_code}",
        "rawPath": f"/v1/flow/canonical/operations/{operation_code}",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": qp,
        "pathParameters": {"operationCode": operation_code},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _flow_draft_validate_event(body: dict) -> dict:
    """Build POST /v1/flow/draft/validate event."""
    return {
        "path": "/v1/flow/draft/validate",
        "rawPath": "/v1/flow/draft/validate",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


# --- Flow operations endpoints ---


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_flow_operations_list_returns_canonical_registry(_mock_auth: object) -> None:
    """GET /v1/flow/canonical/operations returns items from canonical_registry."""
    event = _flow_operations_list_event()
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert "items" in body
    assert isinstance(body["items"], list)
    ops = {item["operationCode"]: item for item in body["items"]}
    assert "GET_VERIFY_MEMBER_ELIGIBILITY" in ops
    assert "GET_MEMBER_ACCUMULATORS" in ops
    assert ops["GET_VERIFY_MEMBER_ELIGIBILITY"]["latestVersion"] == "1.0"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_flow_operation_detail_returns_operation_detail(_mock_auth: object) -> None:
    """GET /v1/flow/canonical/operations/{operationCode} returns operation details."""
    event = _flow_operation_detail_event("GET_VERIFY_MEMBER_ELIGIBILITY")
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert body["version"] == "1.0"
    assert "requestPayloadSchema" in body
    assert "responsePayloadSchema" in body
    assert "examples" in body


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_flow_operation_detail_version_alias(_mock_auth: object) -> None:
    """GET with ?version=v1 resolves to official version 1.0."""
    event = _flow_operation_detail_event("GET_VERIFY_MEMBER_ELIGIBILITY")
    event["queryStringParameters"] = {"version": "v1"}
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["version"] == "1.0"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_flow_operation_not_found_returns_404(_mock_auth: object) -> None:
    """GET /v1/flow/canonical/operations/{operationCode} returns 404 for unknown operation."""
    event = _flow_operation_detail_event("UNKNOWN_OPERATION_XYZ")
    result = handler(event, None)
    assert result["statusCode"] == 404
    body = json.loads(result["body"])
    assert "error" in body
    assert body["error"]["code"] == "NOT_FOUND"


# --- Flow draft validation ---


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_flow_draft_valid_passes(_mock_auth: object) -> None:
    """Valid draft passes validation and returns normalized draft."""
    body = {
        "name": "Eligibility Check Flow",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "trigger": {"type": "MANUAL"},
        "mappingMode": "CANONICAL_FIRST",
        "notes": "optional",
    }
    event = _flow_draft_validate_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    data = json.loads(result["body"])
    assert data["valid"] is True
    assert "normalizedDraft" in data
    nd = data["normalizedDraft"]
    assert nd["name"] == "Eligibility Check Flow"
    assert nd["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert nd["version"] == "1.0"
    assert nd["sourceVendor"] == "LH001"
    assert nd["targetVendor"] == "LH002"
    assert nd["trigger"]["type"] == "MANUAL"
    assert nd["mappingMode"] == "CANONICAL_FIRST"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_flow_draft_missing_name_fails(_mock_auth: object) -> None:
    """Missing name fails validation."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "trigger": {"type": "MANUAL"},
        "mappingMode": "CANONICAL_FIRST",
    }
    event = _flow_draft_validate_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    data = json.loads(result["body"])
    assert data["valid"] is False
    assert "errors" in data
    assert any("name" in str(e).lower() for e in data["errors"])


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_flow_draft_missing_source_vendor_fails(_mock_auth: object) -> None:
    """Missing sourceVendor fails validation."""
    body = {
        "name": "Test",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "targetVendor": "LH002",
        "trigger": {"type": "MANUAL"},
        "mappingMode": "CANONICAL_FIRST",
    }
    event = _flow_draft_validate_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    data = json.loads(result["body"])
    assert data["valid"] is False
    assert any("source" in str(e).lower() for e in data["errors"])


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_flow_draft_missing_target_vendor_fails(_mock_auth: object) -> None:
    """Missing targetVendor fails validation."""
    body = {
        "name": "Test",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "trigger": {"type": "MANUAL"},
        "mappingMode": "CANONICAL_FIRST",
    }
    event = _flow_draft_validate_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    data = json.loads(result["body"])
    assert data["valid"] is False
    assert any("target" in str(e).lower() for e in data["errors"])


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_flow_draft_invalid_trigger_type_fails(_mock_auth: object) -> None:
    """Invalid trigger.type fails validation."""
    body = {
        "name": "Test",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "trigger": {"type": "SCHEDULED"},
        "mappingMode": "CANONICAL_FIRST",
    }
    event = _flow_draft_validate_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    data = json.loads(result["body"])
    assert data["valid"] is False
    assert any("trigger" in str(e).lower() for e in data["errors"])


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_flow_draft_invalid_mapping_mode_fails(_mock_auth: object) -> None:
    """Invalid mappingMode fails validation."""
    body = {
        "name": "Test",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "trigger": {"type": "MANUAL"},
        "mappingMode": "CUSTOM",
    }
    event = _flow_draft_validate_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    data = json.loads(result["body"])
    assert data["valid"] is False
    assert any("mapping" in str(e).lower() for e in data["errors"])


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_flow_draft_unknown_operation_code_fails(_mock_auth: object) -> None:
    """Unknown operationCode fails validation."""
    body = {
        "name": "Test",
        "operationCode": "UNKNOWN_OP_XYZ",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "trigger": {"type": "MANUAL"},
        "mappingMode": "CANONICAL_FIRST",
    }
    event = _flow_draft_validate_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    data = json.loads(result["body"])
    assert data["valid"] is False
    assert any("operation" in str(e).lower() or "not found" in str(e).lower() for e in data["errors"])


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_flow_draft_version_alias_normalizes_to_1_0(_mock_auth: object) -> None:
    """Version alias v1 normalizes to 1.0."""
    body = {
        "name": "Test",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "v1",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "trigger": {"type": "MANUAL"},
        "mappingMode": "CANONICAL_FIRST",
    }
    event = _flow_draft_validate_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    data = json.loads(result["body"])
    assert data["valid"] is True
    assert data["normalizedDraft"]["version"] == "1.0"
