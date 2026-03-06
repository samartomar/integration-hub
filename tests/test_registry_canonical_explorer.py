"""Unit tests for Registry Lambda canonical explorer endpoints."""

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


def _canonical_operations_list_event() -> dict:
    """Build GET /v1/registry/canonical/operations event."""
    return {
        "path": "/v1/registry/canonical/operations",
        "rawPath": "/v1/registry/canonical/operations",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _canonical_operation_detail_event(
    operation_code: str, version: str | None = None
) -> dict:
    """Build GET /v1/registry/canonical/operations/{operationCode} event."""
    qp = {"version": version} if version else {}
    return {
        "path": f"/v1/registry/canonical/operations/{operation_code}",
        "rawPath": f"/v1/registry/canonical/operations/{operation_code}",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": qp,
        "pathParameters": {"operationCode": operation_code},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_canonical_operations_list_returns_registry_data(_mock_auth: object) -> None:
    """GET /v1/registry/canonical/operations returns items from canonical_registry."""
    event = _canonical_operations_list_event()
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert "items" in body
    assert isinstance(body["items"], list)
    # GET_VERIFY_MEMBER_ELIGIBILITY v1 is registered
    ops = {item["operationCode"]: item for item in body["items"]}
    assert "GET_VERIFY_MEMBER_ELIGIBILITY" in ops
    assert ops["GET_VERIFY_MEMBER_ELIGIBILITY"]["latestVersion"] == "1.0"
    # List item contract: operationCode, latestVersion, title, description, versions
    for item in body["items"]:
        assert "operationCode" in item
        assert "latestVersion" in item
        assert "versions" in item
        assert isinstance(item["versions"], list)


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_canonical_operation_detail_returns_schemas_and_examples(_mock_auth: object) -> None:
    """GET /v1/registry/canonical/operations/{operationCode} returns operation details."""
    event = _canonical_operation_detail_event("GET_VERIFY_MEMBER_ELIGIBILITY")
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert body["version"] == "1.0"
    assert "requestPayloadSchema" in body
    assert "responsePayloadSchema" in body
    assert "examples" in body
    assert "request" in body["examples"]
    assert "response" in body["examples"]
    assert body["requestPayloadSchema"]["required"] == ["memberIdWithPrefix", "date"]
    assert body["responsePayloadSchema"]["required"] == ["memberIdWithPrefix", "name", "dob", "status"]
    assert body["examples"]["request"]["memberIdWithPrefix"] == "LH001-12345"
    assert body["examples"]["response"]["status"] == "ACTIVE"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_canonical_operation_not_found_returns_404(_mock_auth: object) -> None:
    """GET /v1/registry/canonical/operations/{operationCode} returns 404 for unknown operation."""
    event = _canonical_operation_detail_event("UNKNOWN_OPERATION_XYZ")
    result = handler(event, None)
    assert result["statusCode"] == 404
    body = json.loads(result["body"])
    assert "error" in body
    assert body["error"]["code"] == "NOT_FOUND"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_canonical_operation_detail_version_1_0_eligibility(_mock_auth: object) -> None:
    """GET eligibility with ?version=1.0 returns official version."""
    event = _canonical_operation_detail_event("GET_VERIFY_MEMBER_ELIGIBILITY", "1.0")
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["version"] == "1.0"
    assert "requestEnvelope" in body.get("examples", {})
    assert "responseEnvelope" in body.get("examples", {})


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_canonical_operation_detail_resolves_version_alias(_mock_auth: object) -> None:
    """GET with ?version=v1 resolves to official version 1.0."""
    event = _canonical_operation_detail_event("GET_VERIFY_MEMBER_ELIGIBILITY")
    event["queryStringParameters"] = {"version": "v1"}
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["version"] == "1.0"
    assert body["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_canonical_operation_detail_includes_title_description(_mock_auth: object) -> None:
    """Operation detail includes title and description when present."""
    event = _canonical_operation_detail_event("GET_VERIFY_MEMBER_ELIGIBILITY")
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body.get("title") == "Verify Member Eligibility"
    assert "description" in body


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_canonical_operations_list_includes_both_operations(_mock_auth: object) -> None:
    """List returns both GET_VERIFY_MEMBER_ELIGIBILITY and GET_MEMBER_ACCUMULATORS."""
    event = _canonical_operations_list_event()
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    ops = {item["operationCode"]: item for item in body["items"]}
    assert "GET_VERIFY_MEMBER_ELIGIBILITY" in ops
    assert "GET_MEMBER_ACCUMULATORS" in ops
    assert ops["GET_MEMBER_ACCUMULATORS"].get("title") == "Get Member Accumulators"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_canonical_operation_accumulators_detail_version_1_0(_mock_auth: object) -> None:
    """GET accumulators with version=1.0 returns schemas and envelope examples."""
    event = _canonical_operation_detail_event("GET_MEMBER_ACCUMULATORS", "1.0")
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["operationCode"] == "GET_MEMBER_ACCUMULATORS"
    assert body["version"] == "1.0"
    assert "individualDeductible" in str(body.get("responsePayloadSchema", {}))
    assert "requestEnvelope" in body.get("examples", {})
    assert "responseEnvelope" in body.get("examples", {})


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_canonical_operation_accumulators_detail_version_v1(_mock_auth: object) -> None:
    """GET accumulators with version=v1 resolves to 1.0."""
    event = _canonical_operation_detail_event("GET_MEMBER_ACCUMULATORS")
    event["queryStringParameters"] = {"version": "v1"}
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["version"] == "1.0"
