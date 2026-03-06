"""Tests for Canonical Execute backend endpoint."""

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
    "jwt": {"claims": {"sub": "okta|test", "aud": "api://default", "bcpAuth": "LH001", "groups": ["admins"]}},
}
AUTH_REQUEST_CONTEXT = {"http": {"method": "POST"}, "authorizer": JWT_AUTHORIZER}


def _execute_event(body: dict) -> dict:
    """Build POST /v1/runtime/canonical/execute event."""
    return {
        "path": "/v1/runtime/canonical/execute",
        "rawPath": "/v1/runtime/canonical/execute",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_canonical_execute_dry_run_success(_mock_auth: object) -> None:
    """POST /v1/runtime/canonical/execute DRY_RUN returns preflight + preview."""
    event = _execute_event({
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "DRY_RUN",
        "envelope": {
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "v1",
            "direction": "REQUEST",
            "correlationId": "corr-test",
            "timestamp": "2025-03-06T12:00:00Z",
            "context": {},
            "payload": {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"},
        },
    })
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["mode"] == "DRY_RUN"
    assert body["valid"] is True
    assert body["status"] == "READY"
    assert "executeRequestPreview" in body
    assert "preflight" in body
    assert body["executeRequestPreview"]["targetVendor"] == "LH002"
    assert body["executeRequestPreview"]["operation"] == "GET_VERIFY_MEMBER_ELIGIBILITY"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_canonical_execute_malformed_json_returns_400(_mock_auth: object) -> None:
    """Malformed JSON body returns 400."""
    event = _execute_event({"sourceVendor": "LH001", "targetVendor": "LH002", "mode": "DRY_RUN", "envelope": {}})
    event["body"] = "not valid json{{{"
    result = handler(event, None)
    assert result["statusCode"] == 400


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_canonical_execute_blocked_preflight_returns_blocked(_mock_auth: object) -> None:
    """Invalid preflight returns BLOCKED without executing."""
    event = _execute_event({
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": {
            "operationCode": "UNKNOWN_OP_XYZ",
            "version": "1.0",
            "direction": "REQUEST",
            "correlationId": "corr",
            "timestamp": "2025-03-06T12:00:00Z",
            "context": {},
            "payload": {},
        },
    })
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["status"] == "BLOCKED"
    assert body["valid"] is False
