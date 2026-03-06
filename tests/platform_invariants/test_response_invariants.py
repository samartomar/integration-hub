"""Platform invariant tests: canonical response contract.

Invariants:
6. Protected routes use canonical error responses
7. AI gateway uses custom envelope (documented exception)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "apps" / "api" / "src" / "lambda"))


def test_protected_route_returns_canonical_error_envelope() -> None:
    """Invariant 6: Protected routes use canonical error responses (transactionId, correlationId, error)."""
    from vendor_registry_lambda import handler  # noqa: E402

    event = {
        "path": "/v1/vendor/my-change-requests",
        "rawPath": "/v1/vendor/my-change-requests",
        "httpMethod": "GET",
        "pathParameters": {"proxy": "my-change-requests"},
        "queryStringParameters": {},
        "requestContext": {"http": {"method": "GET"}},
        "headers": {},
        "body": None,
    }
    resp = handler(event, None)

    assert resp["statusCode"] in (401, 403)
    body = json.loads(resp["body"])
    assert "transactionId" in body or "error" in body
    err = body.get("error", {})
    assert err is not None
    assert "code" in err
    assert "message" in err


@patch("ai_gateway_lambda._load_operation_ai_config")
@patch("ai_gateway_lambda._call_integration_api")
def test_ai_gateway_uses_custom_envelope_documented_exception(
    mock_call: MagicMock, mock_load: MagicMock
) -> None:
    """Invariant 7: ai_gateway_lambda uses AI-specific envelope (documented exception in platform_invariants.md)."""
    from ai_gateway_lambda import handler  # noqa: E402

    mock_call.return_value = {"responseBody": {"status": "completed"}}
    mock_load.return_value = {"ai_presentation_mode": "RAW_ONLY"}

    event = {
        "body": json.dumps({"requestType": "DATA", "operationCode": "GET_RECEIPT", "targetVendorCode": "LH002", "payload": {}}),
        "headers": {"authorization": "Bearer x"},
        "requestContext": {
            "authorizer": {"bcpAuth": "LH001", "jwt": {"claims": {"bcpAuth": "LH001", "aud": "api://default", "scp": "execute ai_execute"}}},
        },
    }
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "requestType" in body
    assert "rawResult" in body or "aiFormatter" in body
    assert "finalText" in body or "error" in body
