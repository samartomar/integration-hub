"""Tests for AI Debugger backend endpoints."""

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
AUTH_REQUEST_CONTEXT = {"http": {"method": "POST"}, "authorizer": JWT_AUTHORIZER}


def _ai_debug_request_analyze_event(body: dict) -> dict:
    """Build POST /v1/ai/debug/request/analyze event."""
    return {
        "path": "/v1/ai/debug/request/analyze",
        "rawPath": "/v1/ai/debug/request/analyze",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _ai_debug_flow_draft_analyze_event(body: dict) -> dict:
    """Build POST /v1/ai/debug/flow-draft/analyze event."""
    return {
        "path": "/v1/ai/debug/flow-draft/analyze",
        "rawPath": "/v1/ai/debug/flow-draft/analyze",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _ai_debug_sandbox_result_analyze_event(body: dict) -> dict:
    """Build POST /v1/ai/debug/sandbox-result/analyze event."""
    return {
        "path": "/v1/ai/debug/sandbox-result/analyze",
        "rawPath": "/v1/ai/debug/sandbox-result/analyze",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_ai_debug_request_analyze_success(_mock_auth: object) -> None:
    """POST /v1/ai/debug/request/analyze success case."""
    event = _ai_debug_request_analyze_event({
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "v1",
        "payload": {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"},
    })
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["debugType"] == "CANONICAL_REQUEST"
    assert body["status"] == "PASS"
    assert body["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert "summary" in body
    assert "findings" in body
    assert "notes" in body


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_ai_debug_request_analyze_invalid_payload(_mock_auth: object) -> None:
    """POST /v1/ai/debug/request/analyze with invalid payload returns 200 with FAIL status."""
    event = _ai_debug_request_analyze_event({
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "payload": {"memberIdWithPrefix": "LH001-12345", "date": "invalid-date"},
    })
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["status"] == "FAIL"
    assert any(f["code"] == "INVALID_DATE_FORMAT" for f in body.get("findings", []))


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_ai_debug_request_analyze_malformed_body(_mock_auth: object) -> None:
    """POST /v1/ai/debug/request/analyze with malformed body returns 400."""
    event = _ai_debug_request_analyze_event({"operationCode": "X", "payload": "not-an-object"})
    result = handler(event, None)
    assert result["statusCode"] == 400


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_ai_debug_flow_draft_analyze_success(_mock_auth: object) -> None:
    """POST /v1/ai/debug/flow-draft/analyze success case."""
    event = _ai_debug_flow_draft_analyze_event({
        "draft": {
            "name": "Eligibility Flow",
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
            "sourceVendor": "LH001",
            "targetVendor": "LH002",
            "trigger": {"type": "MANUAL"},
            "mappingMode": "CANONICAL_FIRST",
        },
    })
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["debugType"] == "FLOW_DRAFT"
    assert body["status"] == "PASS"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_ai_debug_flow_draft_analyze_invalid(_mock_auth: object) -> None:
    """POST /v1/ai/debug/flow-draft/analyze with invalid draft returns 200 with FAIL."""
    event = _ai_debug_flow_draft_analyze_event({
        "draft": {
            "name": "",
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
            "sourceVendor": "LH001",
            "targetVendor": "LH002",
            "trigger": {"type": "MANUAL"},
            "mappingMode": "CANONICAL_FIRST",
        },
    })
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["status"] == "FAIL"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_ai_debug_sandbox_result_analyze_success(_mock_auth: object) -> None:
    """POST /v1/ai/debug/sandbox-result/analyze success case."""
    event = _ai_debug_sandbox_result_analyze_event({
        "result": {
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
            "mode": "MOCK",
            "valid": True,
            "requestEnvelope": {"payload": {}},
            "responseEnvelope": {"payload": {}},
        },
    })
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["debugType"] == "SANDBOX_RESULT"
    assert body["status"] == "PASS"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_ai_debug_sandbox_result_analyze_invalid(_mock_auth: object) -> None:
    """POST /v1/ai/debug/sandbox-result/analyze with invalid result returns 200 with findings."""
    event = _ai_debug_sandbox_result_analyze_event({
        "result": {
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
            "valid": False,
            "errors": [{"field": "payload", "message": "Invalid"}],
        },
    })
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["status"] == "FAIL"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_ai_debug_request_analyze_malformed_json(_mock_auth: object) -> None:
    """Malformed request body returns repo-consistent 400."""
    event = _ai_debug_request_analyze_event({})
    event["body"] = "not valid json{{{"
    result = handler(event, None)
    assert result["statusCode"] == 400
