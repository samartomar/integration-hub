"""Unit tests for Runtime API: /v1/execute and /v1/ai/execute."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))


def _runtime_execute_event(body: dict, headers: dict | None = None) -> dict:
    """Event for Runtime API POST /v1/execute."""
    h = dict(headers) if headers is not None else {}
    if headers is None:
        h.setdefault("authorization", "Bearer test-token")
    h.setdefault("content-type", "application/json")
    return {
        "path": "/v1/execute",
        "rawPath": "/v1/execute",
        "httpMethod": "POST",
        "pathParameters": {},
        "requestContext": {
            "http": {"method": "POST"},
            "authorizer": {
                "bcpAuth": "LH001",
                "principalId": "LH001",
                "jwt": {"claims": {"bcpAuth": "LH001", "aud": "api://default", "scp": "execute ai_execute"}},
            },
        },
        "headers": h,
        "body": json.dumps(body),
    }


# --- /v1/execute via routing lambda ---


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_runtime_execute_happy_path(
    mock_validate: MagicMock,
    mock_conn_ctx: MagicMock,
    mock_idempotency_lookup: MagicMock,
    mock_load_version: MagicMock,
    mock_load_contract: MagicMock,
    mock_load_mapping: MagicMock,
    mock_call_downstream: MagicMock,
) -> None:
    """Runtime /v1/execute: valid JWT authorizer context -> 200, correct response."""
    from routing_lambda import handler  # noqa: E402

    mock_validate.return_value = {
        "url": "http://example.com/op",
        "http_method": "POST",
        "timeout_ms": 8000,
        "canonical_version": "v1",
    }
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "request_schema": None,
        "response_schema": None,
    }
    mock_load_mapping.side_effect = lambda c, v, o, ver, d, flow_direction="OUTBOUND": (
        {"result": "$.result"} if "CANONICAL_RESPONSE" in d else {"transactionId": "$.transactionId"}
    )
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("LH001", True), ("tx-123",)]
    mock_cursor.execute.side_effect = None

    body = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "operation": "GET_RECEIPT",
        "parameters": {"transactionId": "tx-1"},
        "includeActuals": True,
    }
    event = _runtime_execute_event(body)
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    out = json.loads(resp["body"])
    assert "transactionId" in out
    assert "correlationId" in out
    rb = out.get("responseBody", {})
    assert rb.get("status") == "completed"
    assert rb.get("responseBody", {}).get("result") == "ok"
    mock_validate.assert_called_once()
    assert mock_validate.call_args[0][1] == "LH001"
    assert mock_validate.call_args[0][2] == "LH002"


def test_runtime_execute_auth_failure_missing_jwt() -> None:
    """Runtime /v1/execute: missing JWT context -> 401 AUTH_ERROR."""
    from routing_lambda import handler  # noqa: E402

    body = {"sourceVendor": "LH001", "targetVendor": "LH002", "operation": "GET_RECEIPT", "parameters": {}}
    event = _runtime_execute_event(body, headers={})
    event["requestContext"] = {"http": {"method": "POST"}}
    resp = handler(event, None)

    assert resp["statusCode"] == 401
    out = json.loads(resp["body"])
    err = out.get("error", {})
    assert err.get("code") == "AUTH_ERROR"
    assert err.get("category") == "AUTH"


# --- /v1/ai/execute DATA mode (uses Runtime /v1/execute when RUNTIME_API_URL set) ---


@patch.dict("os.environ", {"RUNTIME_API_URL": "https://runtime.example.com", "AI_GATEWAY_SOURCE_VENDOR": "LH001"}, clear=False)
@patch("ai_gateway_lambda._call_integration_api")
@patch("ai_gateway_lambda._load_operation_ai_config")
def test_ai_execute_data_uses_runtime_api(
    mock_load_op: MagicMock,
    mock_call_hub: MagicMock,
) -> None:
    """AI /v1/ai/execute DATA: when RUNTIME_API_URL set, calls runtime /v1/execute; response has envelope."""
    from ai_gateway_lambda import handler  # noqa: E402

    mock_load_op.return_value = {"ai_presentation_mode": "RAW_ONLY", "ai_formatter_prompt": None, "ai_formatter_model": None}
    mock_call_hub.return_value = {
        "transactionId": "tx-ai-1",
        "correlationId": "corr-ai-1",
        "responseBody": {"status": "completed", "receiptId": "R-456"},
    }

    event = {
        "body": json.dumps({
            "requestType": "DATA",
            "operationCode": "GET_RECEIPT",
            "targetVendorCode": "LH002",
            "payload": {"txnId": "123"},
            "aiFormatter": False,
        }),
        "headers": {"authorization": "Bearer test-token"},
        "requestContext": {
            "authorizer": {
                "bcpAuth": "LH001",
                "jwt": {"claims": {"bcpAuth": "LH001", "aud": "api://default", "scp": "execute ai_execute"}},
            }
        },
    }
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["requestType"] == "DATA"
    assert body["rawResult"]["responseBody"]["receiptId"] == "R-456"
    assert body["aiFormatter"]["applied"] is False
    assert body["finalText"] is None
    assert body["error"] is None
    mock_call_hub.assert_called_once()
    call_kw = mock_call_hub.call_args[1]
    assert call_kw.get("use_runtime_api") is True
    assert call_kw.get("source_vendor") == "LH001"


@patch("ai_gateway_lambda._invoke_bedrock_agent")
def test_ai_execute_prompt_mode_unchanged(mock_invoke_agent: MagicMock) -> None:
    """AI /v1/ai/execute PROMPT: behavior unchanged; finalText from agent."""
    from ai_gateway_lambda import handler  # noqa: E402

    mock_invoke_agent.return_value = "It is 72F and sunny."

    event = {
        "body": json.dumps({"requestType": "PROMPT", "prompt": "What's the weather?"}),
        "headers": {"authorization": "Bearer test-token"},
        "requestContext": {
            "authorizer": {
                "bcpAuth": "LH001",
                "jwt": {"claims": {"bcpAuth": "LH001", "aud": "api://default", "scp": "execute ai_execute"}},
            }
        },
    }
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["requestType"] == "PROMPT"
    assert body["finalText"] == "It is 72F and sunny."
    assert body["aiFormatter"]["applied"] is False