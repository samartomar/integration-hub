"""Unit tests for Central AI Endpoint POST /v1/ai/execute."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add apps/api/src/lambda to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

# Set env before importing handler (auth and config).
# Do NOT set DB_SECRET_ARN here: it pollutes os.environ and causes integration tests
# (allowlist, migration smoke) to run in CI with invalid ARN, triggering GetSecretValue errors.
os.environ["VENDOR_API_URL"] = "https://api.example.com/prod"
os.environ.setdefault("AI_ENDPOINT_ENABLED", "true")

from ai_gateway_lambda import handler  # noqa: E402


@pytest.fixture(autouse=True)
def _gate_enabled_default() -> None:
    with patch("ai_gateway_lambda._is_ai_feature_enabled", return_value=True):
        yield


def _event(body: dict, headers: dict | None = None) -> dict:
    h = headers or {}
    return {
        "body": json.dumps(body),
        "headers": {k: v for k, v in h.items()},
        "requestContext": {
            "authorizer": {
                "jwt": {"claims": {"bcpAuth": "LH001", "aud": "api://default", "scp": ["ai_execute"]}},
                "bcpAuth": "LH001",
                "principalId": "LH001",
            }
        },
    }


# --- DATA + aiFormatter=false ---


@patch("ai_gateway_lambda._call_integration_api")
@patch("ai_gateway_lambda._load_operation_ai_config")
def test_data_ai_formatter_false(
    mock_load_op: MagicMock,
    mock_call_hub: MagicMock,
) -> None:
    """DATA + aiFormatter=false: rawResult present, aiFormatter.applied=False."""
    mock_load_op.return_value = {
        "ai_presentation_mode": "RAW_AND_FORMATTED",
        "ai_formatter_prompt": None,
        "ai_formatter_model": None,
    }
    mock_call_hub.return_value = {
        "transactionId": "tx-1",
        "correlationId": "corr-1",
        "responseBody": {"foo": "bar"},
    }

    event = _event({
        "requestType": "DATA",
        "operationCode": "GET_WEATHER",
        "targetVendorCode": "LH001",
        "payload": {},
        "aiFormatter": False,
    })
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["requestType"] == "DATA"
    assert body["operationCode"] == "GET_WEATHER"
    assert body["targetVendorCode"] == "LH001"
    assert body["rawResult"]["responseBody"]["foo"] == "bar"
    assert body["aiFormatter"]["applied"] is False
    assert body["aiFormatter"]["reason"] == "REQUEST_DISABLED"
    assert body["finalText"] is None
    assert body["error"] is None


@patch("ai_gateway_lambda._call_integration_api")
@patch("ai_gateway_lambda._load_operation_ai_config")
def test_data_get_receipt_ai_formatter_false(
    mock_load_op: MagicMock,
    mock_call_hub: MagicMock,
) -> None:
    """DATA + GET_RECEIPT + aiFormatter=false: rawResult has receiptId."""
    mock_load_op.return_value = {
        "ai_presentation_mode": "RAW_ONLY",
        "ai_formatter_prompt": None,
        "ai_formatter_model": None,
    }
    mock_call_hub.return_value = {
        "transactionId": "tx-rec",
        "correlationId": "corr-rec",
        "responseBody": {"status": "OK", "receiptId": "R-123"},
    }

    event = _event({
        "requestType": "DATA",
        "operationCode": "GET_RECEIPT",
        "targetVendorCode": "LH001",
        "payload": {"txnId": "123"},
        "aiFormatter": False,
    })
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["requestType"] == "DATA"
    assert body["operationCode"] == "GET_RECEIPT"
    assert body["rawResult"]["responseBody"]["receiptId"] == "R-123"
    assert body["aiFormatter"]["applied"] is False
    assert body["aiFormatter"]["reason"] == "MODE_RAW_ONLY"
    assert body["finalText"] is None
    assert body["error"] is None


# --- DATA + aiFormatter=true + RAW_AND_FORMATTED ---


@patch("ai_gateway_lambda.call_formatter_model")
@patch("ai_gateway_lambda._call_integration_api")
@patch("ai_gateway_lambda._load_operation_ai_config")
def test_data_ai_formatter_true_raw_and_formatted(
    mock_load_op: MagicMock,
    mock_call_hub: MagicMock,
    mock_formatter: MagicMock,
) -> None:
    """DATA + aiFormatter=true + RAW_AND_FORMATTED: formatter applied."""
    mock_load_op.return_value = {
        "ai_presentation_mode": "RAW_AND_FORMATTED",
        "ai_formatter_prompt": "Summarize for voice.",
        "ai_formatter_model": "anthropic.claude-3-haiku-20240307-v1:0",
    }
    mock_call_hub.return_value = {
        "transactionId": "tx-2",
        "correlationId": "corr-2",
        "responseBody": {"temperature": 11, "conditions": "clear"},
    }
    mock_formatter.return_value = "Current weather in Chicago: 11°F, clear."

    event = _event({
        "requestType": "DATA",
        "operationCode": "GET_WEATHER",
        "targetVendorCode": "LH001",
        "payload": {},
        "aiFormatter": True,
    })
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["aiFormatter"]["applied"] is True
    assert body["aiFormatter"]["formattedText"] == "Current weather in Chicago: 11°F, clear."
    assert body["finalText"] == "Current weather in Chicago: 11°F, clear."
    mock_formatter.assert_called_once()


# --- DATA + aiFormatter=true but RAW_ONLY (GET_RECEIPT) ---


@patch("ai_gateway_lambda.call_formatter_model")
@patch("ai_gateway_lambda._call_integration_api")
@patch("ai_gateway_lambda._load_operation_ai_config")
def test_data_ai_formatter_true_raw_only(
    mock_load_op: MagicMock,
    mock_call_hub: MagicMock,
    mock_formatter: MagicMock,
) -> None:
    """DATA + aiFormatter=true but RAW_ONLY (GET_RECEIPT): formatter not applied, no Bedrock call."""
    mock_load_op.return_value = {
        "ai_presentation_mode": "RAW_ONLY",
        "ai_formatter_prompt": None,
        "ai_formatter_model": None,
    }
    mock_call_hub.return_value = {
        "transactionId": "tx-3",
        "correlationId": "corr-3",
        "responseBody": {"status": "OK", "receiptId": "R-123"},
    }

    event = _event({
        "requestType": "DATA",
        "operationCode": "GET_RECEIPT",
        "targetVendorCode": "LH001",
        "payload": {"txnId": "123"},
        "aiFormatter": True,
    })
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["aiFormatter"]["applied"] is False
    assert body["aiFormatter"]["mode"] == "RAW_ONLY"
    assert body["aiFormatter"]["model"] is None
    assert body["aiFormatter"]["reason"] == "MODE_RAW_ONLY"
    assert body["aiFormatter"]["formattedText"] is None
    assert body["finalText"] is None
    assert body["rawResult"]["responseBody"]["receiptId"] == "R-123"
    mock_formatter.assert_not_called()


# --- DATA + hub error ---


@patch("ai_gateway_lambda._call_integration_api")
@patch("ai_gateway_lambda._load_operation_ai_config")
def test_data_hub_error(
    mock_load_op: MagicMock,
    mock_call_hub: MagicMock,
) -> None:
    """DATA + hub returns 400: HTTP 400, rawResult has hub error, aiFormatter.applied=False."""
    import io
    import urllib.error

    mock_load_op.return_value = {
        "ai_presentation_mode": "RAW_ONLY",
        "ai_formatter_prompt": None,
        "ai_formatter_model": None,
    }
    hub_error_body = json.dumps({
        "transactionId": "hub-tx",
        "correlationId": "hub-corr",
        "error": {
            "code": "SCHEMA_VALIDATION_FAILED",
            "message": "Invalid payload",
            "category": "VALIDATION",
            "retryable": False,
        },
    })
    mock_call_hub.side_effect = urllib.error.HTTPError(
        "https://api.example.com/v1/integrations/execute",
        400,
        "Bad Request",
        {},
        io.BytesIO(hub_error_body.encode()),
    )

    event = _event({
        "requestType": "DATA",
        "operationCode": "GET_RECEIPT",
        "targetVendorCode": "LH001",
        "payload": {},
        "aiFormatter": True,
    })
    resp = handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body["requestType"] == "DATA"
    assert body["operationCode"] == "GET_RECEIPT"
    assert body["error"]["code"] == "SCHEMA_VALIDATION_FAILED"
    assert body["rawResult"]["error"]["code"] == "SCHEMA_VALIDATION_FAILED"
    assert body["aiFormatter"]["applied"] is False
    assert body["finalText"] is None


# --- Formatter failure fallback ---


@patch("ai_gateway_lambda.call_formatter_model")
@patch("ai_gateway_lambda._call_integration_api")
@patch("ai_gateway_lambda._load_operation_ai_config")
def test_formatter_failure_fallback(
    mock_load_op: MagicMock,
    mock_call_hub: MagicMock,
    mock_formatter: MagicMock,
) -> None:
    """Formatter failure: HTTP 200, rawResult present, aiFormatter.applied=False, finalText=null, error=null."""
    mock_load_op.return_value = {
        "ai_presentation_mode": "RAW_AND_FORMATTED",
        "ai_formatter_prompt": None,
        "ai_formatter_model": None,
    }
    mock_call_hub.return_value = {
        "transactionId": "tx-4",
        "correlationId": "corr-4",
        "responseBody": {"ok": True},
    }
    from ai_formatter import FormatterError  # noqa: E402

    mock_formatter.side_effect = FormatterError("Bedrock failed", "model-x")

    event = _event({
        "requestType": "DATA",
        "operationCode": "GET_WEATHER",
        "targetVendorCode": "LH001",
        "payload": {},
        "aiFormatter": True,
    })
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["rawResult"] is not None
    assert body["rawResult"]["responseBody"]["ok"] is True
    assert body["aiFormatter"]["applied"] is False
    assert body["aiFormatter"]["formattedText"] is None
    assert body["aiFormatter"]["reason"] == "FORMATTER_ERROR"
    assert body["finalText"] is None
    assert body["error"] is None


def test_data_raw_only_response_has_formatter_applied_false() -> None:
    """DATA + RAW_ONLY + aiFormatter=true: applied=False, finalText=None, rawResult present."""
    import ai_gateway_lambda  # noqa: E402
    with patch.object(ai_gateway_lambda, "_load_operation_ai_config") as mock_load:
        with patch.object(ai_gateway_lambda, "_call_integration_api") as mock_hub:
            mock_load.return_value = {
                "ai_presentation_mode": "RAW_ONLY",
                "ai_formatter_prompt": None,
                "ai_formatter_model": None,
            }
            mock_hub.return_value = {
                "transactionId": "tx-raw",
                "correlationId": "corr-raw",
                "responseBody": {"data": "raw"},
            }
            event = _event({
                "requestType": "DATA",
                "operationCode": "GET_WEATHER",
                "targetVendorCode": "LH001",
                "payload": {},
                "aiFormatter": True,
            })
            resp = ai_gateway_lambda.handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["aiFormatter"]["applied"] is False
    assert body["aiFormatter"]["reason"] == "MODE_RAW_ONLY"
    assert body["finalText"] is None
    assert body["rawResult"]["responseBody"]["data"] == "raw"


# --- PROMPT mode ---


@patch("ai_gateway_lambda._invoke_bedrock_agent")
def test_prompt_mode(mock_invoke_agent: MagicMock) -> None:
    """PROMPT: finalText from agent, aiFormatter.applied=False."""
    mock_invoke_agent.return_value = "It is currently 11°F in Chicago."

    event = _event({
        "requestType": "PROMPT",
        "prompt": "What's the weather in Chicago?",
    })
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["requestType"] == "PROMPT"
    assert body["finalText"] == "It is currently 11°F in Chicago."
    assert body["aiFormatter"]["applied"] is False
    assert body["aiFormatter"]["reason"] == "PROMPT_MODE"
    assert body["aiFormatter"]["mode"] is None
    assert body["aiFormatter"]["model"] is None
    assert body["aiFormatter"]["formattedText"] is None
    mock_invoke_agent.assert_called_once()


# --- Validation errors ---


def test_validation_missing_prompt_propt() -> None:
    """Missing/empty prompt when requestType=PROMPT -> 400 VALIDATION_ERROR."""
    event = _event({"requestType": "PROMPT", "prompt": ""})
    resp = handler(event, None)
    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "VALIDATION_ERROR"
    assert err.get("category") == "VALIDATION"
    assert "prompt" in (err.get("message") or "").lower()


def test_validation_missing_target_vendor_code_data() -> None:
    """Missing targetVendorCode when requestType=DATA -> 400."""
    event = _event({
        "requestType": "DATA",
        "operationCode": "GET_WEATHER",
        "payload": {},
    })
    resp = handler(event, None)
    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "VALIDATION_ERROR"
    assert "targetVendorCode" in (body.get("error", {}).get("message") or "")


def test_validation_missing_payload_data() -> None:
    """Missing payload when requestType=DATA -> 400."""
    event = _event({
        "requestType": "DATA",
        "operationCode": "GET_WEATHER",
        "targetVendorCode": "LH001",
    })
    resp = handler(event, None)
    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "VALIDATION_ERROR"
    assert "payload" in (body.get("error", {}).get("message") or "").lower()


def test_validation_prompt_too_long() -> None:
    """Prompt exceeds max length -> 400."""
    long_prompt = "x" * 9000  # exceeds default 8192
    event = _event({"requestType": "PROMPT", "prompt": long_prompt})
    resp = handler(event, None)
    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "VALIDATION_ERROR"
    assert "prompt" in (body.get("error", {}).get("message") or "").lower()


@patch("ai_gateway_lambda._MAX_BODY_BYTES", 30)
def test_validation_body_too_large() -> None:
    """Request body exceeds max size -> 400."""
    event = _event({
        "requestType": "PROMPT",
        "prompt": "Hello",
    })
    resp = handler(event, None)
    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "VALIDATION_ERROR"
    assert "size" in (body.get("error", {}).get("message") or "").lower()


def test_validation_missing_operation_code_data() -> None:
    """Missing operationCode when requestType=DATA -> 400."""
    event = _event({
        "requestType": "DATA",
        "targetVendorCode": "LH001",
        "payload": {},
    })
    resp = handler(event, None)
    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert "operationCode" in (body.get("error", {}).get("message") or "").lower() or "required" in (body.get("error", {}).get("message") or "").lower()


def test_validation_non_object_payload() -> None:
    """payload must be object -> 400."""
    event = _event({
        "requestType": "DATA",
        "operationCode": "GET_WEATHER",
        "targetVendorCode": "LH001",
        "payload": [],
    })
    resp = handler(event, None)
    assert resp["statusCode"] == 400


def test_validation_ai_formatter_object_not_supported() -> None:
    event = _event({
        "requestType": "DATA",
        "operationCode": "GET_WEATHER",
        "targetVendorCode": "LH001",
        "payload": {},
        "aiFormatter": {"mode": "AUTO"},
    })
    resp = handler(event, None)
    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "VALIDATION_ERROR"
    assert "aiFormatter" in (body.get("error", {}).get("message") or "")


def test_validation_invalid_request_type() -> None:
    """Invalid requestType -> 400."""
    event = _event({
        "requestType": "INVALID",
        "prompt": "Hello",
    })
    resp = handler(event, None)
    assert resp["statusCode"] == 400


def test_auth_missing_secret() -> None:
    """Missing JWT authorizer context -> 401 UNAUTHORIZED. Response uses AI envelope."""
    event = _event({"requestType": "PROMPT", "prompt": "Hi"}, headers={})
    event["headers"] = {}
    event["requestContext"] = {}
    resp = handler(event, None)
    assert resp["statusCode"] == 401
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "UNAUTHORIZED"
    assert body.get("error", {}).get("category") == "AUTH"
    assert "rawResult" in body
    assert "aiFormatter" in body
    assert body["aiFormatter"]["applied"] is False
    assert "finalText" in body
    assert "responseBody" not in body  # No top-level responseBody (AI envelope, not proxy)


def test_auth_invalid_secret() -> None:
    """Invalid auth (no valid JWT): 401."""
    event = _event({"requestType": "PROMPT", "prompt": "Hi"}, headers={"Authorization": "Bearer invalid"})
    event["requestContext"] = {}
    resp = handler(event, None)
    assert resp["statusCode"] == 401
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "UNAUTHORIZED"
    assert "rawResult" in body
    assert "aiFormatter" in body


# --- DATA → Runtime execute forwarding and error handling ---


@patch.dict(
    "ai_gateway_lambda.os.environ",
    {
        "RUNTIME_API_URL": "https://runtime.example.com/prod",
        "AI_GATEWAY_SOURCE_VENDOR": "LH001",
    },
    clear=False,
)
@patch("ai_gateway_lambda.urllib.request.urlopen")
@patch("ai_gateway_lambda._load_operation_ai_config")
def test_ai_execute_data_forwards_authorization_header(
    mock_load_op: MagicMock,
    mock_urlopen: MagicMock,
) -> None:
    """DATA + Runtime: HTTP call forwards Authorization bearer token."""
    mock_load_op.return_value = {
        "ai_presentation_mode": "RAW_ONLY",
        "ai_formatter_prompt": None,
        "ai_formatter_model": None,
    }
    response_body = json.dumps({
        "transactionId": "tx-runtime",
        "correlationId": "corr-runtime",
        "responseBody": {"receiptId": "R-789"},
    }).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.read.return_value = response_body
    mock_resp.status = 200
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = mock_resp

    event = _event({
        "requestType": "DATA",
        "operationCode": "GET_RECEIPT",
        "targetVendorCode": "LH001",
        "payload": {"txnId": "123"},
        "aiFormatter": False,
    })
    event["headers"]["authorization"] = "Bearer token-123"
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["error"] is None
    assert body["rawResult"]["responseBody"]["receiptId"] == "R-789"

    mock_urlopen.assert_called_once()
    call_args = mock_urlopen.call_args[0]
    req = call_args[0]
    headers_dict = {k.lower(): v for k, v in req.header_items()}
    assert headers_dict.get("authorization") == "Bearer token-123", (
        f"Expected Authorization header; got {headers_dict}"
    )
    assert req.full_url.endswith("/v1/execute")
    assert "/prod/v1/execute" in req.full_url or req.full_url == "https://runtime.example.com/prod/v1/execute"


@patch.dict(
    "ai_gateway_lambda.os.environ",
    {
        "RUNTIME_API_URL": "https://runtime.example.com",
        "AI_GATEWAY_SOURCE_VENDOR": "LH001",
    },
    clear=False,
)
@patch("ai_gateway_lambda._load_operation_ai_config")
def test_ai_execute_data_forbidden_from_runtime_surfaces_integration_api_error(
    mock_load_op: MagicMock,
) -> None:
    """DATA + Runtime 403: returns INTEGRATION_API_ERROR, rawResult has message."""
    import io
    import urllib.error

    mock_load_op.return_value = {
        "ai_presentation_mode": "RAW_ONLY",
        "ai_formatter_prompt": None,
        "ai_formatter_model": None,
    }
    hub_error_body = json.dumps({"message": "Forbidden"})
    mock_open = MagicMock()
    mock_open.side_effect = urllib.error.HTTPError(
        "https://runtime.example.com/v1/execute",
        403,
        "Forbidden",
        {},
        io.BytesIO(hub_error_body.encode()),
    )
    with patch("ai_gateway_lambda.urllib.request.urlopen", mock_open):
        event = _event({
            "requestType": "DATA",
            "operationCode": "GET_RECEIPT",
            "targetVendorCode": "LH001",
            "payload": {"txnId": "123"},
            "aiFormatter": False,
        })
        event["headers"]["authorization"] = "Bearer runtime-token"
        resp = handler(event, None)

    assert resp["statusCode"] == 403
    body = json.loads(resp["body"])
    assert body["error"]["code"] == "INTEGRATION_API_ERROR"
    assert body["rawResult"]["message"] == "Forbidden"


def test_data_response_has_ai_envelope_no_proxy_shape() -> None:
    """DATA success: response has AI envelope (rawResult, aiFormatter, finalText), never top-level responseBody."""
    import ai_gateway_lambda
    with patch.object(ai_gateway_lambda, "_load_operation_ai_config") as mock_load:
        with patch.object(ai_gateway_lambda, "_call_integration_api") as mock_hub:
            mock_load.return_value = {
                "ai_presentation_mode": "RAW_ONLY",
                "ai_formatter_prompt": None,
                "ai_formatter_model": None,
            }
            mock_hub.return_value = {
                "transactionId": "tx-e",
                "correlationId": "corr-e",
                "responseBody": {"receiptId": "R-999"},
            }
            event = _event({
                "requestType": "DATA",
                "operationCode": "GET_RECEIPT",
                "targetVendorCode": "LH001",
                "payload": {},
                "aiFormatter": False,
            })
            resp = ai_gateway_lambda.handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "rawResult" in body
    assert body["rawResult"]["responseBody"]["receiptId"] == "R-999"
    assert "aiFormatter" in body
    assert "finalText" in body
    assert "error" in body
    assert "responseBody" not in body  # AI envelope: rawResult holds hub response, no top-level responseBody


@patch("ai_gateway_lambda._is_ai_feature_enabled")
@patch("ai_gateway_lambda._call_integration_api")
@patch("ai_gateway_lambda._load_operation_ai_config")
def test_data_ai_feature_disabled_returns_raw_only(
    mock_load_op: MagicMock,
    mock_call_hub: MagicMock,
    mock_feature_enabled: MagicMock,
) -> None:
    mock_feature_enabled.return_value = False
    mock_load_op.return_value = {
        "ai_presentation_mode": "RAW_AND_FORMATTED",
        "ai_formatter_prompt": None,
        "ai_formatter_model": None,
    }
    mock_call_hub.return_value = {
        "transactionId": "tx-feature-off",
        "correlationId": "corr-feature-off",
        "responseBody": {"ok": True},
    }
    event = _event({
        "requestType": "DATA",
        "operationCode": "GET_WEATHER",
        "targetVendorCode": "LH001",
        "payload": {},
        "aiFormatter": True,
    })
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["rawResult"]["responseBody"]["ok"] is True
    assert body["aiFormatter"]["applied"] is False
    assert body["aiFormatter"]["reason"] == "FEATURE_DISABLED"


@patch("ai_gateway_lambda._call_integration_api")
@patch("ai_gateway_lambda._load_operation_ai_config")
def test_data_jwt_claim_source_vendor_overrides_body(
    mock_load_op: MagicMock,
    mock_call_hub: MagicMock,
) -> None:
    mock_load_op.return_value = {
        "ai_presentation_mode": "RAW_ONLY",
        "ai_formatter_prompt": None,
        "ai_formatter_model": None,
    }
    mock_call_hub.return_value = {
        "transactionId": "tx-jwt",
        "correlationId": "corr-jwt",
        "responseBody": {"ok": True},
    }
    event = _event({
        "requestType": "DATA",
        "operationCode": "GET_WEATHER",
        "targetVendorCode": "LH001",
        "sourceVendorCode": "LH999",
        "payload": {},
        "aiFormatter": False,
    })
    event["requestContext"] = {
        "authorizer": {
            "jwt": {"claims": {"bcpAuth": "LH003", "aud": "api://default", "scp": ["ai_execute"]}},
        },
    }
    resp = handler(event, None)
    assert resp["statusCode"] == 403


# --- Internal debugger enrichment (Lambda-to-Lambda invoke) ---


@patch("ai.bedrock_debugger_enricher.enrich_debug_report_with_bedrock")
def test_internal_debugger_enrich_returns_enrichment(mock_enrich: MagicMock) -> None:
    """Internal event action=debugger_enrich returns enrichment dict (no HTTP envelope)."""
    mock_enrich.return_value = {
        "aiSummary": "Fix the date format.",
        "remediationPlan": [{"priority": 1, "title": "Fix date", "reason": "Invalid", "action": "Use YYYY-MM-DD"}],
        "prioritizedNextSteps": ["Fix date"],
        "aiWarnings": ["Advisory only"],
        "modelInfo": {"provider": "bedrock", "modelId": "x", "enhanced": True},
    }
    event = {
        "action": "debugger_enrich",
        "report": {
            "debugType": "CANONICAL_REQUEST",
            "status": "FAIL",
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
            "summary": "Validation failed",
            "findings": [],
            "notes": [],
        },
    }
    result = handler(event, None)
    assert isinstance(result, dict)
    assert "aiSummary" in result
    assert result["aiSummary"] == "Fix the date format."
    assert result["modelInfo"]["enhanced"] is True
    mock_enrich.assert_called_once()


def test_internal_debugger_enrich_invalid_report_returns_fallback() -> None:
    """Internal event with invalid report returns fallback enrichment."""
    event = {"action": "debugger_enrich", "report": "not-a-dict"}
    result = handler(event, None)
    assert isinstance(result, dict)
    assert "aiWarnings" in result
    assert result["modelInfo"]["enhanced"] is False
