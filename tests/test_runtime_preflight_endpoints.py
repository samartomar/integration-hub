"""Tests for Runtime Preflight backend endpoint."""

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


def _preflight_event(body: dict) -> dict:
    """Build POST /v1/runtime/canonical/preflight event."""
    return {
        "path": "/v1/runtime/canonical/preflight",
        "rawPath": "/v1/runtime/canonical/preflight",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_runtime_preflight_success(_mock_auth: object) -> None:
    """POST /v1/runtime/canonical/preflight success case."""
    event = _preflight_event({
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
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
    assert body["valid"] is True
    assert body["status"] in ("READY", "WARN")
    assert body["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert body["canonicalVersion"] == "1.0"
    assert "checks" in body
    assert "executionPlan" in body
    assert "notes" in body
    assert "mappingSummary" in body
    assert body["mappingSummary"]["available"] is True
    assert "vendorRequestPreview" in body
    assert "mappingSummary" in body
    assert body.get("mappingSummary", {}).get("available") is True
    assert "vendorRequestPreview" in body
    assert "mappingSummary" in body
    assert body["mappingSummary"]["available"] is True
    assert "vendorRequestPreview" in body
    # Mapping-aware: LH001->LH002 has deterministic mapping
    assert "mappingSummary" in body
    assert body["mappingSummary"]["available"] is True
    assert "vendorRequestPreview" in body
    assert body["vendorRequestPreview"] == {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"}
    # Mapping-aware: LH001->LH002 eligibility has deterministic mapping
    assert "mappingSummary" in body
    assert body["mappingSummary"]["available"] is True
    assert "vendorRequestPreview" in body
    assert body["vendorRequestPreview"]["memberIdWithPrefix"] == "LH001-12345"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_runtime_preflight_invalid_body_returns_400(_mock_auth: object) -> None:
    """Malformed JSON body: _parse_body_strict raises; handler returns 400."""
    event = _preflight_event({})
    event["body"] = "not valid json{{{"
    result = handler(event, None)
    assert result["statusCode"] == 400


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_runtime_preflight_invalid_payload_returns_blocked(_mock_auth: object) -> None:
    """Invalid payload returns 200 with blocked result."""
    event = _preflight_event({
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": {
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
            "direction": "REQUEST",
            "correlationId": "corr-test",
            "timestamp": "2025-03-06T12:00:00Z",
            "context": {},
            "payload": {"memberIdWithPrefix": "LH001-12345", "date": "invalid-date"},
        },
    })
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["valid"] is False
    assert body["status"] == "BLOCKED"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_runtime_preflight_unknown_operation_returns_blocked(_mock_auth: object) -> None:
    """Unknown operation returns blocked result."""
    event = _preflight_event({
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": {
            "operationCode": "UNKNOWN_OP_XYZ",
            "version": "1.0",
            "direction": "REQUEST",
            "correlationId": "corr-test",
            "timestamp": "2025-03-06T12:00:00Z",
            "context": {},
            "payload": {},
        },
    })
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["valid"] is False
    assert body["status"] == "BLOCKED"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_runtime_preflight_returns_mapping_aware_fields(_mock_auth: object) -> None:
    """Preflight returns mappingSummary and vendorRequestPreview for supported vendor pair."""
    event = _preflight_event({
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": {
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
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
    assert body["valid"] is True
    assert "mappingSummary" in body
    assert body["mappingSummary"].get("available") is True
    assert "vendorRequestPreview" in body
    assert body["vendorRequestPreview"] == {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"}


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_runtime_preflight_alias_version_resolves(_mock_auth: object) -> None:
    """Alias version v1 resolves correctly to 1.0."""
    event = _preflight_event({
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": {
            "operationCode": "GET_MEMBER_ACCUMULATORS",
            "version": "v1",
            "direction": "REQUEST",
            "correlationId": "corr-test",
            "timestamp": "2025-03-06T12:00:00Z",
            "context": {},
            "payload": {"memberIdWithPrefix": "LH001-12345", "asOfDate": "2025-03-06"},
        },
    })
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["canonicalVersion"] == "1.0"
    assert body.get("normalizedEnvelope", {}).get("version") == "1.0"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_runtime_preflight_returns_mapping_aware_fields(_mock_auth: object) -> None:
    """Preflight returns mappingSummary and vendorRequestPreview for LH001->LH002."""
    event = _preflight_event({
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": {
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
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
    assert "mappingSummary" in body
    assert body["mappingSummary"]["available"] is True
    assert "vendorRequestPreview" in body
    assert body["vendorRequestPreview"]["memberIdWithPrefix"] == "LH001-12345"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_runtime_preflight_returns_mapping_aware_fields(_mock_auth: object) -> None:
    """For LH001->LH002 eligibility, preflight returns mappingSummary and vendorRequestPreview."""
    event = _preflight_event({
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": {
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
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
    assert "mappingSummary" in body
    assert body["mappingSummary"].get("available") is True
    assert "vendorRequestPreview" in body
    assert body["vendorRequestPreview"] == {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"}


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_runtime_preflight_returns_mapping_aware_fields(_mock_auth: object) -> None:
    """Preflight returns mappingSummary and vendorRequestPreview for LH001->LH002."""
    event = _preflight_event({
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": {
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
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
    assert "mappingSummary" in body
    assert body["mappingSummary"]["available"] is True
    assert "vendorRequestPreview" in body
    assert body["vendorRequestPreview"].get("memberIdWithPrefix") == "LH001-12345"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_runtime_preflight_returns_mapping_aware_fields(_mock_auth: object) -> None:
    """Preflight returns mappingSummary and vendorRequestPreview for LH001->LH002."""
    event = _preflight_event({
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": {
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
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
    assert "mappingSummary" in body
    assert body["mappingSummary"]["available"] is True
    assert "vendorRequestPreview" in body
    assert body["vendorRequestPreview"].get("memberIdWithPrefix") == "LH001-12345"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_runtime_preflight_returns_mapping_aware_fields(_mock_auth: object) -> None:
    """Preflight returns mappingSummary and vendorRequestPreview for LH001->LH002."""
    event = _preflight_event({
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": {
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
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
    assert body["valid"] is True
    assert "mappingSummary" in body
    assert body["mappingSummary"].get("available") is True
    assert "vendorRequestPreview" in body
    assert body["vendorRequestPreview"].get("memberIdWithPrefix") == "LH001-12345"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_runtime_preflight_returns_mapping_aware_fields(_mock_auth: object) -> None:
    """Preflight returns mappingSummary and vendorRequestPreview for supported vendor pair."""
    event = _preflight_event({
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": {
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
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
    assert body["valid"] is True
    assert "mappingSummary" in body
    assert body["mappingSummary"].get("available") is True
    assert "vendorRequestPreview" in body
    assert body["vendorRequestPreview"].get("memberIdWithPrefix") == "LH001-12345"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_runtime_preflight_returns_mapping_aware_fields(_mock_auth: object) -> None:
    """Preflight returns mappingSummary and vendorRequestPreview for LH001->LH002."""
    event = _preflight_event({
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": {
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
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
    assert body["valid"] is True
    assert "mappingSummary" in body
    assert body["mappingSummary"].get("available") is True
    assert "vendorRequestPreview" in body
    assert body["vendorRequestPreview"].get("memberIdWithPrefix") == "LH001-12345"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_runtime_preflight_returns_mapping_aware_fields(_mock_auth: object) -> None:
    """Preflight returns mappingSummary and vendorRequestPreview for supported vendor pair."""
    event = _preflight_event({
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": {
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
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
    assert "mappingSummary" in body
    assert body["mappingSummary"]["available"] is True
    assert "vendorRequestPreview" in body
    assert body["vendorRequestPreview"] == {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"}


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_runtime_preflight_returns_mapping_aware_fields(_mock_auth: object) -> None:
    """Preflight returns mappingSummary and vendorRequestPreview for supported vendor pair."""
    event = _preflight_event({
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": {
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
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
    assert body["valid"] is True
    assert "mappingSummary" in body
    assert body["mappingSummary"]["available"] is True
    assert body["mappingSummary"]["direction"] == "CANONICAL_TO_VENDOR"
    assert "vendorRequestPreview" in body
    assert body["vendorRequestPreview"]["memberIdWithPrefix"] == "LH001-12345"
    assert body["vendorRequestPreview"]["date"] == "2025-03-06"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_runtime_preflight_returns_mapping_aware_fields(_mock_auth: object) -> None:
    """Preflight returns mappingSummary and vendorRequestPreview for supported vendor pair."""
    event = _preflight_event({
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": {
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
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
    assert body["valid"] is True
    assert "mappingSummary" in body
    assert body["mappingSummary"]["available"] is True
    assert body["mappingSummary"]["direction"] == "CANONICAL_TO_VENDOR"
    assert "vendorRequestPreview" in body
    assert body["vendorRequestPreview"]["memberIdWithPrefix"] == "LH001-12345"
    assert body["vendorRequestPreview"]["date"] == "2025-03-06"


@patch("registry_lambda.require_admin_secret", return_value=None)
def test_post_runtime_preflight_returns_mapping_aware_fields(_mock_auth: object) -> None:
    """Preflight returns mappingSummary and vendorRequestPreview for supported vendor pair."""
    event = _preflight_event({
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": {
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
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
    assert body["valid"] is True
    assert "mappingSummary" in body
    assert body["mappingSummary"]["available"] is True
    assert body["mappingSummary"]["direction"] == "CANONICAL_TO_VENDOR"
    assert "vendorRequestPreview" in body
    assert body["vendorRequestPreview"].get("memberIdWithPrefix") == "LH001-12345"
    assert body["vendorRequestPreview"].get("date") == "2025-03-06"
