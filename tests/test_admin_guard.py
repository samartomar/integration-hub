"""Unit tests for admin_guard - JWT authorizer validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from admin_guard import require_admin_secret  # noqa: E402


def _event(headers: dict | None = None, authorizer: dict | None = None) -> dict:
    """Build minimal HTTP API v2 event with optional headers and authorizer."""
    ev = {
        "path": "/v1/registry/vendors",
        "httpMethod": "GET",
        "headers": headers or {},
        "requestContext": {},
    }
    if authorizer is not None:
        ev["requestContext"]["authorizer"] = authorizer
    return ev


def test_no_authorizer_returns_401() -> None:
    """Missing JWT authorizer returns 401 AUTH_ERROR."""
    event = _event(headers={})
    resp = require_admin_secret(event)

    assert resp is not None
    assert resp["statusCode"] == 401
    body = json.loads(resp["body"])
    assert body["error"]["code"] == "AUTH_ERROR"
    assert body["error"]["message"]
    assert "transactionId" in body
    assert "correlationId" in body


def test_jwt_authorizer_principal_id_returns_none() -> None:
    """When requestContext.authorizer has valid jwt claims, returns None."""
    event = _event(headers={})
    event["requestContext"]["authorizer"] = {
        "principalId": "okta|abc123",
        "jwt": {"claims": {"sub": "okta|abc123", "aud": "api://default", "groups": ["admins", "admin"]}},
    }
    resp = require_admin_secret(event)
    assert resp is None


def test_jwt_authorizer_claims_only_returns_none() -> None:
    """When authorizer has jwt.claims (HTTP API JWT), returns None."""
    event = _event(headers={})
    event["requestContext"]["authorizer"] = {
        "jwt": {"claims": {"sub": "okta|xyz789", "aud": "api://default", "groups": ["admins", "admin"]}}
    }
    resp = require_admin_secret(event)
    assert resp is None


def test_authorizer_denied_returns_401() -> None:
    """When principalId is denied and no claims, returns 401."""
    event = _event(headers={})
    event["requestContext"]["authorizer"] = {"principalId": "denied"}
    resp = require_admin_secret(event)
    assert resp is not None
    assert resp["statusCode"] == 401
    body = json.loads(resp["body"])
    assert body["error"]["code"] == "AUTH_ERROR"