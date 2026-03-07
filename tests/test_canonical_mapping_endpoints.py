"""Tests for Canonical Mapping Engine backend endpoints."""

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


def _mappings_operations_event() -> dict:
    """Build GET /v1/mappings/canonical/operations event."""
    return {
        "path": "/v1/mappings/canonical/operations",
        "rawPath": "/v1/mappings/canonical/operations",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_preview_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/preview event."""
    return {
        "path": "/v1/mappings/canonical/preview",
        "rawPath": "/v1/mappings/canonical/preview",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_validate_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/validate event."""
    return {
        "path": "/v1/mappings/canonical/validate",
        "rawPath": "/v1/mappings/canonical/validate",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_proposal_package_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/proposal-package event."""
    return {
        "path": "/v1/mappings/canonical/proposal-package",
        "rawPath": "/v1/mappings/canonical/proposal-package",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_proposal_package_markdown_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/proposal-package/markdown event."""
    return {
        "path": "/v1/mappings/canonical/proposal-package/markdown",
        "rawPath": "/v1/mappings/canonical/proposal-package/markdown",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_scaffold_bundle_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/scaffold-bundle event."""
    return {
        "path": "/v1/mappings/canonical/scaffold-bundle",
        "rawPath": "/v1/mappings/canonical/scaffold-bundle",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_scaffold_bundle_markdown_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/scaffold-bundle/markdown event."""
    return {
        "path": "/v1/mappings/canonical/scaffold-bundle/markdown",
        "rawPath": "/v1/mappings/canonical/scaffold-bundle/markdown",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_readiness_event(query_params: dict | None = None) -> dict:
    """Build GET /v1/mappings/canonical/readiness event."""
    return {
        "path": "/v1/mappings/canonical/readiness",
        "rawPath": "/v1/mappings/canonical/readiness",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": query_params or {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_readiness_by_operation_event(operation_code: str) -> dict:
    """Build GET /v1/mappings/canonical/readiness/{operationCode} event."""
    return {
        "path": f"/v1/mappings/canonical/readiness/{operation_code}",
        "rawPath": f"/v1/mappings/canonical/readiness/{operation_code}",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "pathParameters": {"operationCode": operation_code},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_scaffold_bundle_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/scaffold-bundle returns scaffold bundle."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "directions": ["CANONICAL_TO_VENDOR", "VENDOR_TO_CANONICAL"],
    }
    event = _mappings_scaffold_bundle_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert resp.get("valid") is True
    bundle = resp.get("scaffoldBundle")
    assert bundle is not None
    assert bundle["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert "mappingDefinitionFile" in bundle
    assert "eligibility" in bundle["mappingDefinitionFile"]
    assert resp.get("mappingDefinitionStub")
    assert resp.get("fixtureStub")
    assert resp.get("testStub")
    assert "notes" in resp


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_scaffold_bundle_markdown_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/scaffold-bundle/markdown returns markdown artifact."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "directions": ["CANONICAL_TO_VENDOR", "VENDOR_TO_CANONICAL"],
    }
    event = _mappings_scaffold_bundle_markdown_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert "markdown" in resp
    assert "GET_VERIFY_MEMBER_ELIGIBILITY" in resp["markdown"]
    assert "notes" in resp


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_scaffold_bundle_malformed_json_returns_400(_mock_auth: object) -> None:
    """POST scaffold-bundle with malformed JSON returns 400."""
    event = _mappings_scaffold_bundle_event({})
    event["body"] = "not valid json {"
    result = handler(event, None)
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert "error" in body
    assert body["error"]["code"] == "INVALID_JSON"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_scaffold_bundle_invalid_input_returns_400(_mock_auth: object) -> None:
    """POST scaffold-bundle with invalid operation returns 400."""
    body = {
        "operationCode": "UNSUPPORTED_OP",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
    }
    event = _mappings_scaffold_bundle_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 400
    resp = json.loads(result["body"])
    assert "error" in resp


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_readiness_success(_mock_auth: object) -> None:
    """GET /v1/mappings/canonical/readiness returns readiness items."""
    event = _mappings_readiness_event()
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert "items" in body
    assert "summary" in body
    assert body["summary"]["total"] >= 2
    items = body["items"]
    ops = {item["operationCode"] for item in items}
    assert "GET_VERIFY_MEMBER_ELIGIBILITY" in ops
    assert "GET_MEMBER_ACCUMULATORS" in ops
    for item in items:
        assert "status" in item
        assert "mappingDefinition" in item
        assert "fixtures" in item
        assert "runtimeReady" in item


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_readiness_filter_by_operation(_mock_auth: object) -> None:
    """GET /v1/mappings/canonical/readiness?operationCode= filters results."""
    event = _mappings_readiness_event({"operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY"})
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    items = body["items"]
    assert all(item["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY" for item in items)


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_readiness_by_operation_success(_mock_auth: object) -> None:
    """GET /v1/mappings/canonical/readiness/{operationCode} returns readiness for that operation."""
    event = _mappings_readiness_by_operation_event("GET_VERIFY_MEMBER_ELIGIBILITY")
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert "items" in body
    assert all(
        item["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY" for item in body["items"]
    )


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_readiness_by_operation_unknown_returns_empty(_mock_auth: object) -> None:
    """GET /v1/mappings/canonical/readiness/{operationCode} for unknown op returns empty items."""
    event = _mappings_readiness_by_operation_event("UNKNOWN_OPERATION")
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["items"] == []
    assert body["summary"]["total"] == 0


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_operations_list_success(_mock_auth: object) -> None:
    """GET /v1/mappings/canonical/operations returns operations with mapping definitions."""
    event = _mappings_operations_event()
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert "items" in body
    items = body["items"]
    assert len(items) >= 2
    ops = {item["operationCode"]: item for item in items}
    assert "GET_VERIFY_MEMBER_ELIGIBILITY" in ops
    assert "GET_MEMBER_ACCUMULATORS" in ops
    assert ops["GET_VERIFY_MEMBER_ELIGIBILITY"]["vendorPairs"] == [{"sourceVendor": "LH001", "targetVendor": "LH002"}]


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_preview_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/preview returns output payload."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "inputPayload": {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"},
    }
    event = _mappings_preview_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert resp["valid"] is True
    assert resp["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert resp["direction"] == "CANONICAL_TO_VENDOR"
    assert resp["outputPayload"] == {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"}
    assert "notes" in resp


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_validate_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/validate returns validation result."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "inputPayload": {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"},
    }
    event = _mappings_validate_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert resp["valid"] is True
    assert resp["mappingAvailable"] is True


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_preview_malformed_json_returns_400(_mock_auth: object) -> None:
    """POST with malformed JSON returns 400."""
    event = _mappings_preview_event({})
    event["body"] = "not valid json {"
    result = handler(event, None)
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert "error" in body
    assert body["error"]["code"] == "INVALID_JSON"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_preview_missing_mapping_returns_valid_false(_mock_auth: object) -> None:
    """POST with unknown vendor pair returns valid=False and error."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "UNKNOWN",
        "targetVendor": "UNKNOWN",
        "direction": "CANONICAL_TO_VENDOR",
        "inputPayload": {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"},
    }
    event = _mappings_preview_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert resp["valid"] is False
    assert "No mapping definition" in str(resp.get("errors", []))


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_preview_invalid_payload_returns_validation_errors(_mock_auth: object) -> None:
    """POST with missing required input field returns violations."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "inputPayload": {"memberIdWithPrefix": "LH001-12345"},  # missing date
    }
    event = _mappings_preview_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert resp["valid"] is False
    assert any("missing path" in str(e).lower() for e in resp.get("errors", []))


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_proposal_package_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/proposal-package returns structured package."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
    }
    event = _mappings_proposal_package_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert resp.get("valid") is True
    pkg = resp.get("proposalPackage")
    assert pkg is not None
    assert pkg["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert "proposalId" in pkg
    assert "reviewChecklist" in pkg
    assert "promotionGuidance" in pkg
    assert "markdown" in resp


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_proposal_package_markdown_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/proposal-package/markdown returns markdown artifact."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
    }
    event = _mappings_proposal_package_markdown_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert "markdown" in resp
    assert "# Mapping Proposal Package" in resp["markdown"]
    assert "GET_VERIFY_MEMBER_ELIGIBILITY" in resp["markdown"]


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_proposal_package_malformed_json_returns_400(_mock_auth: object) -> None:
    """POST proposal-package with malformed JSON returns 400."""
    event = _mappings_proposal_package_event({})
    event["body"] = "not valid json {"
    result = handler(event, None)
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert body.get("error", {}).get("code") == "INVALID_JSON"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_proposal_package_invalid_input_returns_400(_mock_auth: object) -> None:
    """POST proposal-package with missing required fields returns 400."""
    body = {"operationCode": "OP"}
    event = _mappings_proposal_package_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 400
    resp = json.loads(result["body"])
    assert "error" in resp


def _mappings_proposal_package_event(body: dict, path_suffix: str = "") -> dict:
    """Build POST /v1/mappings/canonical/proposal-package or .../proposal-package/markdown event."""
    path = "/v1/mappings/canonical/proposal-package" + path_suffix
    return {
        "path": path,
        "rawPath": path,
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_proposal_package_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/proposal-package returns structured proposal package."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
    }
    event = _mappings_proposal_package_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert resp["valid"] is True
    pkg = resp.get("proposalPackage")
    assert pkg is not None
    assert pkg["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert "proposalId" in pkg
    assert "reviewChecklist" in pkg
    assert "promotionGuidance" in pkg
    assert "markdown" in resp


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_proposal_package_markdown_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/proposal-package/markdown returns markdown artifact."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
    }
    event = _mappings_proposal_package_event(body, "/markdown")
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert "markdown" in resp
    assert "# Mapping Proposal Package" in resp["markdown"]


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_proposal_package_malformed_json_returns_400(_mock_auth: object) -> None:
    """POST proposal-package with malformed JSON returns 400."""
    event = _mappings_proposal_package_event({})
    event["body"] = "not valid json {"
    result = handler(event, None)
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert body["error"]["code"] == "INVALID_JSON"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_proposal_package_invalid_input_returns_400(_mock_auth: object) -> None:
    """POST proposal-package with missing required fields returns 400."""
    body = {"operationCode": "OP", "sourceVendor": "", "targetVendor": "T", "direction": "CANONICAL_TO_VENDOR"}
    event = _mappings_proposal_package_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 400
    resp = json.loads(result["body"])
    assert "error" in resp


def _mappings_promotion_artifact_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/promotion-artifact event."""
    return {
        "path": "/v1/mappings/canonical/promotion-artifact",
        "rawPath": "/v1/mappings/canonical/promotion-artifact",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_promotion_artifact_markdown_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/promotion-artifact/markdown event."""
    return {
        "path": "/v1/mappings/canonical/promotion-artifact/markdown",
        "rawPath": "/v1/mappings/canonical/promotion-artifact/markdown",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/promotion-artifact returns structured promotion artifact."""
    proposal = {
        "proposalId": "test-123",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
    }
    body = {"proposalPackage": proposal}
    event = _mappings_promotion_artifact_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert resp["valid"] is True
    artifact = resp.get("promotionArtifact")
    assert artifact is not None
    assert artifact["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert "targetDefinitionFile" in artifact
    assert "eligibility" in artifact["targetDefinitionFile"]
    assert "pythonSnippet" in resp
    assert "markdown" in resp


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_markdown_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/promotion-artifact/markdown returns markdown artifact."""
    proposal = {
        "proposalId": "test-123",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
    }
    body = {"proposalPackage": proposal}
    event = _mappings_promotion_artifact_markdown_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert "markdown" in resp
    assert "# Mapping Promotion Artifact" in resp["markdown"]


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_malformed_json_returns_400(_mock_auth: object) -> None:
    """POST promotion-artifact with malformed JSON returns 400."""
    event = _mappings_promotion_artifact_event({})
    event["body"] = "not valid json {"
    result = handler(event, None)
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert body.get("error", {}).get("code") == "INVALID_JSON"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_invalid_proposal_returns_400(_mock_auth: object) -> None:
    """POST promotion-artifact with invalid proposal returns 400."""
    body = {"proposalPackage": {"operationCode": "", "sourceVendor": "LH001", "targetVendor": "LH002"}}
    event = _mappings_promotion_artifact_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 400
    resp = json.loads(result["body"])
    assert "error" in resp


def _mappings_promotion_artifact_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/promotion-artifact event."""
    return {
        "path": "/v1/mappings/canonical/promotion-artifact",
        "rawPath": "/v1/mappings/canonical/promotion-artifact",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_promotion_artifact_markdown_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/promotion-artifact/markdown event."""
    return {
        "path": "/v1/mappings/canonical/promotion-artifact/markdown",
        "rawPath": "/v1/mappings/canonical/promotion-artifact/markdown",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/promotion-artifact returns structured promotion artifact."""
    proposal = {
        "proposalId": "test-123",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
    }
    body = {"proposalPackage": proposal}
    event = _mappings_promotion_artifact_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert resp.get("valid") is True
    artifact = resp.get("promotionArtifact")
    assert artifact is not None
    assert artifact["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert "targetDefinitionFile" in artifact
    assert "eligibility" in artifact["targetDefinitionFile"]
    assert "pythonSnippet" in resp
    assert "markdown" in resp


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_markdown_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/promotion-artifact/markdown returns markdown artifact."""
    proposal = {
        "proposalId": "test-123",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
    }
    body = {"proposalPackage": proposal}
    event = _mappings_promotion_artifact_markdown_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert "markdown" in resp
    assert "# Mapping Promotion Artifact" in resp["markdown"]
    assert "proposalId" in resp


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_malformed_json_returns_400(_mock_auth: object) -> None:
    """POST promotion-artifact with malformed JSON returns 400."""
    event = _mappings_promotion_artifact_event({})
    event["body"] = "not valid json {"
    result = handler(event, None)
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert body.get("error", {}).get("code") == "INVALID_JSON"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_invalid_proposal_returns_400(_mock_auth: object) -> None:
    """POST promotion-artifact with invalid proposal returns 400."""
    body = {"proposalPackage": {"operationCode": "OP", "sourceVendor": "", "targetVendor": "T"}}
    event = _mappings_promotion_artifact_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 400
    resp = json.loads(result["body"])
    assert "error" in resp


# --- Certification endpoints ---


def _mappings_fixtures_event() -> dict:
    """Build GET /v1/mappings/canonical/fixtures event."""
    return {
        "path": "/v1/mappings/canonical/fixtures",
        "rawPath": "/v1/mappings/canonical/fixtures",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_certify_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/certify event."""
    return {
        "path": "/v1/mappings/canonical/certify",
        "rawPath": "/v1/mappings/canonical/certify",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_fixtures_success(_mock_auth: object) -> None:
    """GET /v1/mappings/canonical/fixtures returns fixture list."""
    event = _mappings_fixtures_event()
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert "fixtureSet" in resp
    assert "items" in resp
    assert "notes" in resp
    assert len(resp["items"]) >= 2


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/certify returns certification result."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
    }
    event = _mappings_certify_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert resp["valid"] is True
    assert resp["summary"]["status"] == "PASS"
    assert resp["summary"]["passed"] >= 1
    assert "results" in resp
    assert "notes" in resp


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_malformed_json_returns_400(_mock_auth: object) -> None:
    """POST certify with malformed JSON returns 400."""
    event = _mappings_certify_event({})
    event["body"] = "not valid json {"
    result = handler(event, None)
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert body.get("error", {}).get("code") == "INVALID_JSON"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_invalid_input_returns_400(_mock_auth: object) -> None:
    """POST certify with missing required fields returns 400."""
    body = {"operationCode": "OP", "sourceVendor": "", "targetVendor": "T", "direction": "CANONICAL_TO_VENDOR"}
    event = _mappings_certify_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 400
    resp = json.loads(result["body"])
    assert "error" in resp


# --- Certification endpoints ---


def _mappings_fixtures_event() -> dict:
    """Build GET /v1/mappings/canonical/fixtures event."""
    return {
        "path": "/v1/mappings/canonical/fixtures",
        "rawPath": "/v1/mappings/canonical/fixtures",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_certify_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/certify event."""
    return {
        "path": "/v1/mappings/canonical/certify",
        "rawPath": "/v1/mappings/canonical/certify",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_fixtures_success(_mock_auth: object) -> None:
    """GET /v1/mappings/canonical/fixtures returns fixture list."""
    event = _mappings_fixtures_event()
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert "fixtureSet" in resp
    assert "items" in resp
    assert "notes" in resp
    assert len(resp["items"]) >= 2


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/certify returns certification result."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
    }
    event = _mappings_certify_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert resp["valid"] is True
    assert resp["summary"]["status"] == "PASS"
    assert resp["summary"]["passed"] >= 1
    assert "results" in resp
    assert "No runtime execution" in " ".join(resp.get("notes", []))


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_malformed_json_returns_400(_mock_auth: object) -> None:
    """POST certify with malformed JSON returns 400."""
    event = _mappings_certify_event({})
    event["body"] = "not valid json {"
    result = handler(event, None)
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert body.get("error", {}).get("code") == "INVALID_JSON"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_invalid_input_returns_400(_mock_auth: object) -> None:
    """POST certify with missing required fields returns 400."""
    body = {"operationCode": "OP", "sourceVendor": "", "targetVendor": "T", "direction": "CANONICAL_TO_VENDOR"}
    event = _mappings_certify_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 400
    resp = json.loads(result["body"])
    assert "error" in resp


# --- Promotion Artifact endpoints ---


def _mappings_promotion_artifact_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/promotion-artifact event."""
    return {
        "path": "/v1/mappings/canonical/promotion-artifact",
        "rawPath": "/v1/mappings/canonical/promotion-artifact",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_promotion_artifact_markdown_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/promotion-artifact/markdown event."""
    return {
        "path": "/v1/mappings/canonical/promotion-artifact/markdown",
        "rawPath": "/v1/mappings/canonical/promotion-artifact/markdown",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _valid_proposal_package_for_promotion() -> dict:
    return {
        "proposalId": "promo-test-1",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/promotion-artifact returns structured artifact."""
    body = {"proposalPackage": _valid_proposal_package_for_promotion()}
    event = _mappings_promotion_artifact_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert resp.get("valid") is True
    artifact = resp.get("promotionArtifact")
    assert artifact is not None
    assert artifact["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert "targetDefinitionFile" in artifact
    assert "eligibility" in artifact["targetDefinitionFile"]
    assert "pythonSnippet" in resp
    assert "markdown" in resp
    assert "Promotion artifact only" in str(artifact.get("notes", []))


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_markdown_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/promotion-artifact/markdown returns markdown."""
    body = {"proposalPackage": _valid_proposal_package_for_promotion()}
    event = _mappings_promotion_artifact_markdown_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert "markdown" in resp
    assert "# Mapping Promotion Artifact" in resp["markdown"]
    assert "proposalId" in resp or "Target Definition File" in resp["markdown"]


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_malformed_json_returns_400(_mock_auth: object) -> None:
    """POST promotion-artifact with malformed JSON returns 400."""
    event = _mappings_promotion_artifact_event({})
    event["body"] = "not valid json {"
    result = handler(event, None)
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert body.get("error", {}).get("code") == "INVALID_JSON"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_invalid_proposal_returns_400(_mock_auth: object) -> None:
    """POST promotion-artifact with invalid proposal returns 400."""
    body = {"proposalPackage": {"operationCode": "OP", "sourceVendor": "", "targetVendor": "T"}}
    event = _mappings_promotion_artifact_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 400
    resp = json.loads(result["body"])
    assert "error" in resp


# --- Certification endpoints ---


def _mappings_fixtures_event() -> dict:
    """Build GET /v1/mappings/canonical/fixtures event."""
    return {
        "path": "/v1/mappings/canonical/fixtures",
        "rawPath": "/v1/mappings/canonical/fixtures",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_certify_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/certify event."""
    return {
        "path": "/v1/mappings/canonical/certify",
        "rawPath": "/v1/mappings/canonical/certify",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_fixtures_success(_mock_auth: object) -> None:
    """GET /v1/mappings/canonical/fixtures returns fixture list."""
    event = _mappings_fixtures_event()
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert "fixtureSet" in resp
    assert "items" in resp
    assert "notes" in resp
    assert len(resp["items"]) >= 2


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/certify returns certification result."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
    }
    event = _mappings_certify_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert resp["valid"] is True
    assert resp["summary"]["status"] == "PASS"
    assert resp["summary"]["passed"] >= 1
    assert "results" in resp
    assert "notes" in resp


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_malformed_json_returns_400(_mock_auth: object) -> None:
    """POST certify with malformed JSON returns 400."""
    event = _mappings_certify_event({})
    event["body"] = "not valid json {"
    result = handler(event, None)
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert body.get("error", {}).get("code") == "INVALID_JSON"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_invalid_input_returns_400(_mock_auth: object) -> None:
    """POST certify with missing required fields returns 400."""
    body = {"operationCode": "OP", "sourceVendor": "", "targetVendor": "T", "direction": "CANONICAL_TO_VENDOR"}
    event = _mappings_certify_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 400
    resp = json.loads(result["body"])
    assert "error" in resp


# --- Certification endpoints ---


def _mappings_fixtures_event() -> dict:
    """Build GET /v1/mappings/canonical/fixtures event."""
    return {
        "path": "/v1/mappings/canonical/fixtures",
        "rawPath": "/v1/mappings/canonical/fixtures",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_certify_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/certify event."""
    return {
        "path": "/v1/mappings/canonical/certify",
        "rawPath": "/v1/mappings/canonical/certify",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_fixtures_success(_mock_auth: object) -> None:
    """GET /v1/mappings/canonical/fixtures returns fixture list."""
    event = _mappings_fixtures_event()
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert "fixtureSet" in resp
    assert "items" in resp
    assert "notes" in resp
    assert len(resp["items"]) >= 2


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/certify returns certification result."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
    }
    event = _mappings_certify_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert resp["valid"] is True
    assert resp["summary"]["status"] == "PASS"
    assert resp["summary"]["passed"] >= 1
    assert "results" in resp
    assert "No runtime execution" in " ".join(resp.get("notes", []))


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_malformed_json_returns_400(_mock_auth: object) -> None:
    """POST certify with malformed JSON returns 400."""
    event = _mappings_certify_event({})
    event["body"] = "not valid json {"
    result = handler(event, None)
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert body.get("error", {}).get("code") == "INVALID_JSON"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_invalid_input_returns_400(_mock_auth: object) -> None:
    """POST certify with missing required fields returns 400."""
    body = {"operationCode": "OP", "sourceVendor": "", "targetVendor": "T", "direction": "CANONICAL_TO_VENDOR"}
    event = _mappings_certify_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 400
    resp = json.loads(result["body"])
    assert "error" in resp


def _mappings_proposal_package_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/proposal-package event."""
    return {
        "path": "/v1/mappings/canonical/proposal-package",
        "rawPath": "/v1/mappings/canonical/proposal-package",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_proposal_package_markdown_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/proposal-package/markdown event."""
    return {
        "path": "/v1/mappings/canonical/proposal-package/markdown",
        "rawPath": "/v1/mappings/canonical/proposal-package/markdown",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_proposal_package_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/proposal-package returns structured proposal package."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
    }
    event = _mappings_proposal_package_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert resp["valid"] is True
    pkg = resp.get("proposalPackage")
    assert pkg is not None
    assert pkg["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert pkg["version"] == "1.0"
    assert "proposalId" in pkg
    assert "reviewChecklist" in pkg
    assert "promotionGuidance" in pkg
    assert "markdown" in resp


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_proposal_package_markdown_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/proposal-package/markdown returns markdown artifact."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
    }
    event = _mappings_proposal_package_markdown_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert "markdown" in resp
    assert "# Mapping Proposal Package" in resp["markdown"]
    assert "proposalId" in resp


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_proposal_package_malformed_json_returns_400(_mock_auth: object) -> None:
    """POST proposal-package with malformed JSON returns 400."""
    event = _mappings_proposal_package_event({})
    event["body"] = "not valid json {"
    result = handler(event, None)
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert body["error"]["code"] == "INVALID_JSON"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_proposal_package_invalid_input_returns_400(_mock_auth: object) -> None:
    """POST proposal-package with missing required fields returns 400."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "sourceVendor": "",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {},
    }
    event = _mappings_proposal_package_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 400
    resp = json.loads(result["body"])
    assert "error" in resp


def _mappings_proposal_package_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/proposal-package event."""
    return {
        "path": "/v1/mappings/canonical/proposal-package",
        "rawPath": "/v1/mappings/canonical/proposal-package",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_proposal_package_markdown_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/proposal-package/markdown event."""
    return {
        "path": "/v1/mappings/canonical/proposal-package/markdown",
        "rawPath": "/v1/mappings/canonical/proposal-package/markdown",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_proposal_package_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/proposal-package returns structured proposal package."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
    }
    event = _mappings_proposal_package_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert resp["valid"] is True
    pkg = resp.get("proposalPackage")
    assert pkg is not None
    assert pkg["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert pkg["version"] == "1.0"
    assert "proposalId" in pkg
    assert "reviewChecklist" in pkg
    assert "promotionGuidance" in pkg
    assert "markdown" in resp


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_proposal_package_markdown_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/proposal-package/markdown returns markdown artifact."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
    }
    event = _mappings_proposal_package_markdown_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert "markdown" in resp
    assert "# Mapping Proposal Package" in resp["markdown"]
    assert "GET_VERIFY_MEMBER_ELIGIBILITY" in resp["markdown"]


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_proposal_package_malformed_json_returns_400(_mock_auth: object) -> None:
    """POST proposal-package with malformed JSON returns 400."""
    event = _mappings_proposal_package_event({})
    event["body"] = "not valid json {"
    result = handler(event, None)
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert "error" in body
    assert body["error"]["code"] == "INVALID_JSON"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_proposal_package_invalid_input_returns_400(_mock_auth: object) -> None:
    """POST proposal-package with missing required fields returns 400."""
    body = {"operationCode": "OP", "sourceVendor": "", "targetVendor": "T", "direction": "CANONICAL_TO_VENDOR"}
    event = _mappings_proposal_package_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 400
    resp = json.loads(result["body"])
    assert "error" in resp


def _mappings_promotion_artifact_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/promotion-artifact event."""
    return {
        "path": "/v1/mappings/canonical/promotion-artifact",
        "rawPath": "/v1/mappings/canonical/promotion-artifact",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_promotion_artifact_markdown_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/promotion-artifact/markdown event."""
    return {
        "path": "/v1/mappings/canonical/promotion-artifact/markdown",
        "rawPath": "/v1/mappings/canonical/promotion-artifact/markdown",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/promotion-artifact returns structured promotion artifact."""
    proposal = {
        "proposalId": "test-123",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
    }
    body = {"proposalPackage": proposal}
    event = _mappings_promotion_artifact_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert resp["valid"] is True
    artifact = resp.get("promotionArtifact")
    assert artifact is not None
    assert artifact["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert "targetDefinitionFile" in artifact
    assert "eligibility" in artifact["targetDefinitionFile"]
    assert "pythonSnippet" in resp
    assert "markdown" in resp


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_markdown_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/promotion-artifact/markdown returns markdown artifact."""
    proposal = {
        "proposalId": "test-123",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
    }
    body = {"proposalPackage": proposal}
    event = _mappings_promotion_artifact_markdown_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert "markdown" in resp
    assert "# Mapping Promotion Artifact" in resp["markdown"]


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_malformed_json_returns_400(_mock_auth: object) -> None:
    """POST promotion-artifact with malformed JSON returns 400."""
    event = _mappings_promotion_artifact_event({})
    event["body"] = "not valid json {"
    result = handler(event, None)
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert body.get("error", {}).get("code") == "INVALID_JSON"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_invalid_proposal_returns_400(_mock_auth: object) -> None:
    """POST promotion-artifact with invalid proposal returns 400."""
    body = {"proposalPackage": {"operationCode": "", "sourceVendor": "LH001", "targetVendor": "LH002"}}
    event = _mappings_promotion_artifact_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 400
    resp = json.loads(result["body"])
    assert "error" in resp


def _mappings_promotion_artifact_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/promotion-artifact event."""
    return {
        "path": "/v1/mappings/canonical/promotion-artifact",
        "rawPath": "/v1/mappings/canonical/promotion-artifact",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_promotion_artifact_markdown_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/promotion-artifact/markdown event."""
    return {
        "path": "/v1/mappings/canonical/promotion-artifact/markdown",
        "rawPath": "/v1/mappings/canonical/promotion-artifact/markdown",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/promotion-artifact returns structured promotion artifact."""
    proposal = {
        "proposalId": "test-123",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
    }
    body = {"proposalPackage": proposal}
    event = _mappings_promotion_artifact_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert resp.get("valid") is True
    artifact = resp.get("promotionArtifact")
    assert artifact is not None
    assert artifact["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert "targetDefinitionFile" in artifact
    assert "eligibility" in artifact["targetDefinitionFile"]
    assert "pythonSnippet" in resp
    assert "markdown" in resp


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_markdown_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/promotion-artifact/markdown returns markdown artifact."""
    proposal = {
        "proposalId": "test-123",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
    }
    body = {"proposalPackage": proposal}
    event = _mappings_promotion_artifact_markdown_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert "markdown" in resp
    assert "# Mapping Promotion Artifact" in resp["markdown"]
    assert "proposalId" in resp


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_malformed_json_returns_400(_mock_auth: object) -> None:
    """POST promotion-artifact with malformed JSON returns 400."""
    event = _mappings_promotion_artifact_event({})
    event["body"] = "not valid json {"
    result = handler(event, None)
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert body.get("error", {}).get("code") == "INVALID_JSON"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_invalid_proposal_returns_400(_mock_auth: object) -> None:
    """POST promotion-artifact with invalid proposal returns 400."""
    body = {"proposalPackage": {"operationCode": "OP", "sourceVendor": "", "targetVendor": "T"}}
    event = _mappings_promotion_artifact_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 400
    resp = json.loads(result["body"])
    assert "error" in resp


# --- Certification endpoints ---


def _mappings_fixtures_event() -> dict:
    """Build GET /v1/mappings/canonical/fixtures event."""
    return {
        "path": "/v1/mappings/canonical/fixtures",
        "rawPath": "/v1/mappings/canonical/fixtures",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_certify_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/certify event."""
    return {
        "path": "/v1/mappings/canonical/certify",
        "rawPath": "/v1/mappings/canonical/certify",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_fixtures_success(_mock_auth: object) -> None:
    """GET /v1/mappings/canonical/fixtures returns fixture list."""
    event = _mappings_fixtures_event()
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert "fixtureSet" in resp
    assert "items" in resp
    assert "notes" in resp
    assert len(resp["items"]) >= 2


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/certify returns certification result."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
    }
    event = _mappings_certify_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert resp["valid"] is True
    assert resp["summary"]["status"] == "PASS"
    assert resp["summary"]["passed"] >= 1
    assert "results" in resp
    assert "notes" in resp


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_malformed_json_returns_400(_mock_auth: object) -> None:
    """POST certify with malformed JSON returns 400."""
    event = _mappings_certify_event({})
    event["body"] = "not valid json {"
    result = handler(event, None)
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert body.get("error", {}).get("code") == "INVALID_JSON"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_invalid_input_returns_400(_mock_auth: object) -> None:
    """POST certify with missing required fields returns 400."""
    body = {"operationCode": "OP", "sourceVendor": "", "targetVendor": "T", "direction": "CANONICAL_TO_VENDOR"}
    event = _mappings_certify_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 400
    resp = json.loads(result["body"])
    assert "error" in resp


# --- Certification endpoints ---


def _mappings_fixtures_event() -> dict:
    """Build GET /v1/mappings/canonical/fixtures event."""
    return {
        "path": "/v1/mappings/canonical/fixtures",
        "rawPath": "/v1/mappings/canonical/fixtures",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_certify_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/certify event."""
    return {
        "path": "/v1/mappings/canonical/certify",
        "rawPath": "/v1/mappings/canonical/certify",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_fixtures_success(_mock_auth: object) -> None:
    """GET /v1/mappings/canonical/fixtures returns fixture list."""
    event = _mappings_fixtures_event()
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert "fixtureSet" in resp
    assert "items" in resp
    assert "notes" in resp
    assert len(resp["items"]) >= 2


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/certify returns certification result."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
    }
    event = _mappings_certify_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert resp["valid"] is True
    assert resp["summary"]["status"] == "PASS"
    assert resp["summary"]["passed"] >= 1
    assert "results" in resp
    assert "No runtime execution" in " ".join(resp.get("notes", []))


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_malformed_json_returns_400(_mock_auth: object) -> None:
    """POST certify with malformed JSON returns 400."""
    event = _mappings_certify_event({})
    event["body"] = "not valid json {"
    result = handler(event, None)
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert body.get("error", {}).get("code") == "INVALID_JSON"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_invalid_input_returns_400(_mock_auth: object) -> None:
    """POST certify with missing required fields returns 400."""
    body = {"operationCode": "OP", "sourceVendor": "", "targetVendor": "T", "direction": "CANONICAL_TO_VENDOR"}
    event = _mappings_certify_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 400
    resp = json.loads(result["body"])
    assert "error" in resp


# --- Promotion Artifact endpoints ---


def _mappings_promotion_artifact_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/promotion-artifact event."""
    return {
        "path": "/v1/mappings/canonical/promotion-artifact",
        "rawPath": "/v1/mappings/canonical/promotion-artifact",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_promotion_artifact_markdown_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/promotion-artifact/markdown event."""
    return {
        "path": "/v1/mappings/canonical/promotion-artifact/markdown",
        "rawPath": "/v1/mappings/canonical/promotion-artifact/markdown",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _valid_proposal_package_for_promotion() -> dict:
    return {
        "proposalId": "promo-test-1",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/promotion-artifact returns structured artifact."""
    body = {"proposalPackage": _valid_proposal_package_for_promotion()}
    event = _mappings_promotion_artifact_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert resp.get("valid") is True
    artifact = resp.get("promotionArtifact")
    assert artifact is not None
    assert artifact["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert "targetDefinitionFile" in artifact
    assert "eligibility" in artifact["targetDefinitionFile"]
    assert "pythonSnippet" in resp
    assert "markdown" in resp
    assert "Promotion artifact only" in str(artifact.get("notes", []))


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_markdown_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/promotion-artifact/markdown returns markdown."""
    body = {"proposalPackage": _valid_proposal_package_for_promotion()}
    event = _mappings_promotion_artifact_markdown_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert "markdown" in resp
    assert "# Mapping Promotion Artifact" in resp["markdown"]
    assert "proposalId" in resp or "Target Definition File" in resp["markdown"]


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_malformed_json_returns_400(_mock_auth: object) -> None:
    """POST promotion-artifact with malformed JSON returns 400."""
    event = _mappings_promotion_artifact_event({})
    event["body"] = "not valid json {"
    result = handler(event, None)
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert body.get("error", {}).get("code") == "INVALID_JSON"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_promotion_artifact_invalid_proposal_returns_400(_mock_auth: object) -> None:
    """POST promotion-artifact with invalid proposal returns 400."""
    body = {"proposalPackage": {"operationCode": "OP", "sourceVendor": "", "targetVendor": "T"}}
    event = _mappings_promotion_artifact_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 400
    resp = json.loads(result["body"])
    assert "error" in resp


# --- Certification endpoints ---


def _mappings_fixtures_event() -> dict:
    """Build GET /v1/mappings/canonical/fixtures event."""
    return {
        "path": "/v1/mappings/canonical/fixtures",
        "rawPath": "/v1/mappings/canonical/fixtures",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_certify_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/certify event."""
    return {
        "path": "/v1/mappings/canonical/certify",
        "rawPath": "/v1/mappings/canonical/certify",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_fixtures_success(_mock_auth: object) -> None:
    """GET /v1/mappings/canonical/fixtures returns fixture list."""
    event = _mappings_fixtures_event()
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert "fixtureSet" in resp
    assert "items" in resp
    assert "notes" in resp
    assert len(resp["items"]) >= 2


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/certify returns certification result."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
    }
    event = _mappings_certify_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert resp["valid"] is True
    assert resp["summary"]["status"] == "PASS"
    assert resp["summary"]["passed"] >= 1
    assert "results" in resp
    assert "notes" in resp


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_malformed_json_returns_400(_mock_auth: object) -> None:
    """POST certify with malformed JSON returns 400."""
    event = _mappings_certify_event({})
    event["body"] = "not valid json {"
    result = handler(event, None)
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert body.get("error", {}).get("code") == "INVALID_JSON"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_invalid_input_returns_400(_mock_auth: object) -> None:
    """POST certify with missing required fields returns 400."""
    body = {"operationCode": "OP", "sourceVendor": "", "targetVendor": "T", "direction": "CANONICAL_TO_VENDOR"}
    event = _mappings_certify_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 400
    resp = json.loads(result["body"])
    assert "error" in resp


# --- Certification endpoints ---


def _mappings_fixtures_event() -> dict:
    """Build GET /v1/mappings/canonical/fixtures event."""
    return {
        "path": "/v1/mappings/canonical/fixtures",
        "rawPath": "/v1/mappings/canonical/fixtures",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mappings_certify_event(body: dict) -> dict:
    """Build POST /v1/mappings/canonical/certify event."""
    return {
        "path": "/v1/mappings/canonical/certify",
        "rawPath": "/v1/mappings/canonical/certify",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_fixtures_success(_mock_auth: object) -> None:
    """GET /v1/mappings/canonical/fixtures returns fixture list."""
    event = _mappings_fixtures_event()
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert "fixtureSet" in resp
    assert "items" in resp
    assert "notes" in resp
    assert len(resp["items"]) >= 2


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_success(_mock_auth: object) -> None:
    """POST /v1/mappings/canonical/certify returns certification result."""
    body = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
    }
    event = _mappings_certify_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 200
    resp = json.loads(result["body"])
    assert resp["valid"] is True
    assert resp["summary"]["status"] == "PASS"
    assert resp["summary"]["passed"] >= 1
    assert "results" in resp
    assert "No runtime execution" in " ".join(resp.get("notes", []))


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_malformed_json_returns_400(_mock_auth: object) -> None:
    """POST certify with malformed JSON returns 400."""
    event = _mappings_certify_event({})
    event["body"] = "not valid json {"
    result = handler(event, None)
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert body.get("error", {}).get("code") == "INVALID_JSON"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_mappings_certify_invalid_input_returns_400(_mock_auth: object) -> None:
    """POST certify with missing required fields returns 400."""
    body = {"operationCode": "OP", "sourceVendor": "", "targetVendor": "T", "direction": "CANONICAL_TO_VENDOR"}
    event = _mappings_certify_event(body)
    result = handler(event, None)
    assert result["statusCode"] == 400
    resp = json.loads(result["body"])
    assert "error" in resp
