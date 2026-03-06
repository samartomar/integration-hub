"""Platform invariant tests: identity contract.

Invariants:
1. Runtime blocks vendor spoof when token vendor != request vendor
2. Vendor-scoped route fails if bcpAuth is missing
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "apps" / "api" / "src" / "lambda"))


def _runtime_execute_event(body: dict, authorizer_bcp_auth: str = "LH001") -> dict:
    """Event for Runtime API POST /v1/execute."""
    return {
        "path": "/v1/execute",
        "rawPath": "/v1/execute",
        "httpMethod": "POST",
        "pathParameters": {},
        "requestContext": {
            "http": {"method": "POST"},
            "authorizer": {
                "bcpAuth": authorizer_bcp_auth,
                "principalId": authorizer_bcp_auth,
                "jwt": {"claims": {"bcpAuth": authorizer_bcp_auth, "aud": "api://default", "scp": "execute ai_execute"}},
            },
        },
        "headers": {"content-type": "application/json", "authorization": "Bearer test-token"},
        "body": json.dumps(body),
    }


def test_runtime_blocks_vendor_spoof_when_token_vendor_mismatches_body() -> None:
    """Invariant 1: Runtime blocks vendor spoof when token vendor != request vendor.

    Behavioral test: policy_engine (used by routing_lambda) denies when
    requested_source_vendor_code from body does not match vendor_code from JWT.
    """
    from policy_engine import PolicyContext, evaluate_policy, VENDOR_SPOOF_BLOCKED  # noqa: E402

    decision = evaluate_policy(
        PolicyContext(
            surface="RUNTIME",
            action="EXECUTE",
            vendor_code="LH001",
            target_vendor_code="LH002",
            operation_code="GET_RECEIPT",
            requested_source_vendor_code="LH999",
            is_admin=False,
            groups=[],
            query={},
        )
    )
    assert decision.allow is False
    assert decision.decision_code == VENDOR_SPOOF_BLOCKED


def test_vendor_scoped_route_fails_without_bcpauth() -> None:
    """Invariant 2: Vendor-scoped route fails if bcpAuth is missing."""
    from vendor_registry_lambda import handler  # noqa: E402

    event = {
        "path": "/v1/vendor/my-change-requests",
        "rawPath": "/v1/vendor/my-change-requests",
        "httpMethod": "GET",
        "pathParameters": {"proxy": "my-change-requests"},
        "queryStringParameters": {"status": "PENDING"},
        "requestContext": {"http": {"method": "GET"}, "requestId": "test"},
        "headers": {},
        "body": None,
    }
    resp = handler(event, None)

    assert resp["statusCode"] in (401, 403)
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err is not None
    assert err.get("code") in ("AUTH_ERROR", "FORBIDDEN", "UNAUTHORIZED")
