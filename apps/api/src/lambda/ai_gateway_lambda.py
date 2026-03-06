"""
Central AI HTTP Endpoint – POST /v1/ai/execute.

Handles two request types:
- PROMPT: Delegates to Bedrock Agent for conversational integration execution.
  Agent reply is returned as finalText. No separate formatter run.
- DATA: Calls Integration Hub synchronous execute, optionally applies AI Formatter.
  rawResult = full Hub response. When formatter applied: formattedText and finalText.
  Formatter failures do not mask successful Integration Hub responses – we return 200
  with rawResult and aiFormatter.applied=false.

Auth: JWT (authorizer) only.
When formatter is applied: uses control_plane.operations (ai_presentation_mode, ai_formatter_model)
and request body aiFormatter (boolean only).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg2
from ai_formatter import (
    AIFormatterReason,
    FormatterDecision,
    FormatterError,
    OperationAiConfig,
    build_local_stub_summary,
    call_formatter_model,
    decide_formatter_action,
)
from bcp_auth import AuthError, validate_authorizer_claims, validate_jwt
from canonical_response import canonical_error
from cors import add_cors_to_response
from feature_flags import is_feature_enabled_for_vendor
from observability import get_context, log_json, with_observability
from psycopg2.extras import RealDictCursor

_SRC_ROOT = Path(__file__).resolve().parent.parent
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))
from shared.policy_engine import evaluate_policy

# Max request body size (bytes)
_MAX_BODY_BYTES = int(os.environ.get("AI_GATEWAY_MAX_BODY_BYTES", "131072"))  # 128 KB
_MAX_PROMPT_CHARS = int(os.environ.get("AI_GATEWAY_MAX_PROMPT_CHARS", "8192"))  # 8 KB
_VALID_CHANNELS = frozenset({"GENERIC", "CONNECT", "WEB_APP", "AGENT_ASSIST"})
_AI_GATE_FEATURE_CODE = "ai_formatter_enabled"
_PROMPT_MODEL_MAX_CHARS = int(os.environ.get("AI_FORMATTER_MAX_PROMPT_CHARS", "4000"))
_FORMATTER_OUTPUT_MAX_CHARS = int(os.environ.get("AI_FORMATTER_MAX_OUTPUT_CHARS", "1200"))


def _auth_header(event: dict[str, Any]) -> str:
    headers = event.get("headers") or {}
    if not isinstance(headers, dict):
        return ""
    for k, v in headers.items():
        if str(k).lower() == "authorization":
            return v if isinstance(v, str) else str(v)
    return ""


def _require_ai_gateway_auth(event: dict[str, Any], required_scope: str | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Validate JWT auth + AI scope and return normalized claims payload."""
    aud = (os.environ.get("RUNTIME_API_AUDIENCE") or os.environ.get("IDP_AUDIENCE") or "api://default").strip()
    try:
        auth = (event.get("requestContext") or {}).get("authorizer") or {}
        jwt_claims = auth.get("jwt", {}).get("claims", {}) if isinstance(auth.get("jwt"), dict) else {}
        if isinstance(jwt_claims, dict) and jwt_claims:
            validated = validate_authorizer_claims(
                jwt_claims,
                expected_audience=aud,
                required_scope=required_scope,
                allow_vendor=True,
            )
        else:
            validated = validate_jwt(
                _auth_header(event),
                expected_audience=aud,
                required_scope=required_scope,
                allow_vendor=True,
            )
        return None, {
            "subject": validated.subject,
            "bcpAuth": validated.bcpAuth,
            "roles": validated.roles,
            "scopes": validated.scopes,
        }
    except AuthError as e:
        status = 403 if e.status_code == 403 else 401
        code = "FORBIDDEN" if status == 403 else "UNAUTHORIZED"
        return canonical_error(
            code, e.message, status_code=status,
            category="AUTH", retryable=False,
        ), None


def _resolve_db_creds() -> dict[str, Any]:
    """Resolve DB credentials from DB_URL or DB_SECRET_ARN."""
    db_url = os.environ.get("DB_URL")
    if db_url:
        return {"connection_string": db_url}
    import urllib.parse

    secret_arn = os.environ.get("DB_SECRET_ARN")
    if not secret_arn:
        raise ConnectionError("Neither DB_URL nor DB_SECRET_ARN is set")
    import boto3  # noqa: PLC0415

    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_arn)
    raw = json.loads(response["SecretString"])
    pw = raw["password"]
    pw_enc = urllib.parse.quote(str(pw), safe="")
    return {
        "connection_string": (
            f"postgresql://{raw.get('username') or raw.get('user')}:{pw_enc}"
            f"@{raw['host']}:{raw.get('port', 5432)}"
            f"/{raw.get('dbname', raw.get('database', 'integrationhub'))}"
        )
    }


@contextmanager
def _get_connection() -> Generator[Any, None, None]:
    """Get Postgres connection for read-only queries."""
    creds = _resolve_db_creds()
    conn = psycopg2.connect(creds["connection_string"], connect_timeout=10)
    try:
        yield conn
    finally:
        conn.close()


def _load_operation_ai_config(operation_code: str) -> OperationAiConfig | None:
    """Load ai_presentation_mode, ai_formatter_prompt, ai_formatter_model from control_plane.operations."""
    try:
        with _get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT ai_presentation_mode, ai_formatter_prompt, ai_formatter_model, canonical_version, direction_policy
                    FROM control_plane.operations
                    WHERE operation_code = %s AND COALESCE(is_active, true)
                    LIMIT 1
                    """,
                    (operation_code,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return {
                    "ai_presentation_mode": row.get("ai_presentation_mode"),
                    "ai_formatter_prompt": row.get("ai_formatter_prompt"),
                    "ai_formatter_model": row.get("ai_formatter_model"),
                    "canonical_version": row.get("canonical_version"),
                }
    except Exception:
        return None


def _is_ai_feature_enabled(vendor_code: str | None) -> bool:
    """Resolve formatter gate with vendor->global fallback; missing rows => disabled."""
    try:
        with _get_connection() as conn:
            return is_feature_enabled_for_vendor(
                conn,
                _AI_GATE_FEATURE_CODE,
                vendor_code,
                default_enabled=False,
            )
    except Exception:
        return False


def _resolve_vendor_from_authorizer(event: dict[str, Any]) -> str | None:
    """Deprecated compatibility shim; use bcpAuth-validated claims instead."""
    _ = event
    return None


def _call_integration_api(
    target_vendor: str,
    operation_code: str,
    payload: dict[str, Any],
    idempotency_key: str | None,
    auth_header: str | None,
    base_url: str,
    *,
    source_vendor: str | None = None,
    use_runtime_api: bool = False,
) -> dict[str, Any]:
    """
    Call Integration Hub execute via Runtime API (POST /v1/execute) only.
    """
    runtime_url = (os.environ.get("RUNTIME_API_URL") or "").strip()
    if use_runtime_api and runtime_url and auth_header:
        base = runtime_url.rstrip("/")
        path = "/v1/execute"
        url = base + path
        envelope: dict[str, Any] = {
            "targetVendor": target_vendor,
            "operation": operation_code,
            "parameters": payload,
        }
        if source_vendor:
            envelope["sourceVendor"] = source_vendor
        if idempotency_key:
            envelope["idempotencyKey"] = idempotency_key
        data = json.dumps(envelope).encode("utf-8")
        # Forward caller JWT to Runtime API.
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Authorization": auth_header,
        }
        log_json(
            "INFO",
            "ai_gateway_runtime_execute_request",
            operationCode=operation_code,
            targetVendorCode=target_vendor,
            runtimeUrl=url,
            hasAuthorization=bool(auth_header),
        )
        req = urllib.request.Request(url, data=data, method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            status_code = getattr(resp, "status", None) or (
                resp.getcode() if hasattr(resp, "getcode") else 200
            )
            log_json(
                "INFO",
                "ai_gateway_runtime_execute_response",
                statusCode=status_code,
                operationCode=operation_code,
                targetVendorCode=target_vendor,
            )
            return json.loads(body) if body else {}
    raise RuntimeError("Runtime API is required for execute (RUNTIME_API_URL + Authorization)")


def _invoke_bedrock_agent(prompt: str) -> str:
    """Invoke Bedrock Agent with prompt. Returns agent reply text."""
    run_env = (os.environ.get("RUN_ENV") or "").strip().lower()
    use_bedrock = (os.environ.get("USE_BEDROCK", "true")).strip().lower() not in ("false", "0")
    if run_env == "local" or not use_bedrock:
        return f"AI (local stub): {prompt[:80]}"
    agent_id = (os.environ.get("BEDROCK_AGENT_ID") or "").strip()
    alias_id = (os.environ.get("BEDROCK_AGENT_ALIAS_ID") or "TSTALIASID").strip()
    if not agent_id:
        raise ValueError("BEDROCK_AGENT_ID not configured")
    import boto3

    region = (os.environ.get("BEDROCK_REGION") or os.environ.get("AWS_REGION") or "us-east-1").strip()
    client = boto3.client("bedrock-agent-runtime", region_name=region)
    session_id = f"ai-gateway-{uuid.uuid4().hex[:12]}"
    response = client.invoke_agent(
        agentId=agent_id,
        agentAliasId=alias_id,
        sessionId=session_id,
        inputText=prompt[: _MAX_PROMPT_CHARS],
    )
    completion = response.get("completion") or []
    chunks: list[str] = []
    for event in completion:
        if "chunk" in event:
            chunk = event["chunk"]
            if isinstance(chunk, dict) and "bytes" in chunk:
                raw = chunk["bytes"]
                if isinstance(raw, bytes):
                    chunks.append(raw.decode("utf-8", errors="replace"))
                elif hasattr(raw, "read"):
                    chunks.append(raw.read().decode("utf-8", errors="replace"))
                else:
                    chunks.append(str(raw))
    return "".join(chunks).strip()


def _validate_request_body(body: dict[str, Any]) -> str | None:
    """Validate request. Returns error message or None if valid."""
    rt = body.get("requestType")
    if not rt or rt not in ("PROMPT", "DATA"):
        return "requestType is required and must be PROMPT or DATA"

    if rt == "PROMPT":
        prompt = body.get("prompt")
        if not prompt or not isinstance(prompt, str):
            return "prompt is required for PROMPT requests"
        if len(prompt.strip()) == 0:
            return "prompt cannot be empty"
        if len(prompt) > _MAX_PROMPT_CHARS:
            return f"prompt exceeds max length ({_MAX_PROMPT_CHARS} chars)"
        channel = body.get("channel")
        if channel and channel not in _VALID_CHANNELS:
            return f"channel must be one of {sorted(_VALID_CHANNELS)}"
        return None

    # DATA
    op = body.get("operationCode")
    if not op or not isinstance(op, str):
        return "operationCode is required for DATA requests"
    target = body.get("targetVendorCode")
    if not target or not isinstance(target, str):
        return "targetVendorCode is required for DATA requests"
    # sourceVendorCode: required when AI gateway calls Runtime /v1/execute (allowlist needs source)
    payload = body.get("payload")
    if payload is None:
        return "payload is required for DATA requests"
    if not isinstance(payload, dict):
        return "payload must be a JSON object"
    channel = body.get("channel")
    if channel and channel not in _VALID_CHANNELS:
        return f"channel must be one of {sorted(_VALID_CHANNELS)}"
    ai_fmt = body.get("aiFormatter")
    if ai_fmt is not None and not isinstance(ai_fmt, bool):
        return "aiFormatter must be boolean"
    return None


def _log_ai_execute_completed(
    status_code: int,
    request_type: str | None = None,
    operation_code: str | None = None,
    target_vendor_code: str | None = None,
    channel: str | None = None,
    transaction_id: str | None = None,
    correlation_id: str | None = None,
    ai_formatter_applied: bool | None = None,
    ai_formatter_mode: str | None = None,
    ai_formatter_model: str | None = None,
    error_code: str | None = None,
    error_category: str | None = None,
    formatted_preview: str | None = None,
) -> None:
    """Emit one structured log per request for observability."""
    log_level = "WARN" if status_code >= 400 else "INFO"
    fields: dict[str, Any] = {
        "event": "ai_execute_completed",
        "requestType": request_type,
        "operationCode": operation_code,
        "targetVendorCode": target_vendor_code,
        "channel": channel,
        "transactionId": transaction_id,
        "correlationId": correlation_id,
        "aiFormatterApplied": ai_formatter_applied,
        "aiFormatterMode": ai_formatter_mode,
        "aiFormatterModel": ai_formatter_model,
        "statusCode": status_code,
    }
    if error_code:
        fields["errorCode"] = error_code
    if error_category:
        fields["errorCategory"] = error_category
    if formatted_preview is not None:
        fields["formattedPreview"] = formatted_preview[:120] if formatted_preview else None
    # Drop None values for cleaner logs
    clean = {k: v for k, v in fields.items() if v is not None}
    log_json(log_level, "ai_execute_completed", **clean)


def _build_response_envelope(
    transaction_id: str,
    correlation_id: str,
    request_type: str,
    operation_code: str | None,
    target_vendor_code: str | None,
    raw_result: dict[str, Any] | None,
    ai_formatter_applied: bool,
    ai_formatter_mode: str | None,
    ai_formatter_model: str | None,
    ai_formatter_reason: str | None,
    ai_formatter_error: str | None,
    formatted_text: str | None,
    final_text: str | None,
    error: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build unified AI envelope (rawResult, aiFormatter, finalText, error). Always used for /v1/ai/execute."""
    out: dict[str, Any] = {
        "transactionId": transaction_id,
        "correlationId": correlation_id,
        "requestType": request_type,
        "rawResult": raw_result,
        "aiFormatter": {
            "applied": ai_formatter_applied,
            "mode": ai_formatter_mode,
            "model": ai_formatter_model,
            "reason": ai_formatter_reason,
            "error": ai_formatter_error,
            "formattedText": formatted_text,
        },
        "finalText": final_text,
        "error": error,
    }
    if operation_code:
        out["operationCode"] = operation_code
    if target_vendor_code:
        out["targetVendorCode"] = target_vendor_code
    return out


def _ai_envelope_error_response(
    code: str,
    message: str,
    status_code: int,
    request_type: str = "DATA",
    operation_code: str | None = None,
    target_vendor_code: str | None = None,
    category: str | None = None,
    retryable: bool | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return HTTP response with AI envelope for early/validation/auth errors."""
    transaction_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    err: dict[str, Any] = {"code": code, "message": message}
    if category is not None:
        err["category"] = category
    if retryable is not None:
        err["retryable"] = retryable
    if details is not None:
        err["details"] = details
    payload = _build_response_envelope(
        transaction_id, correlation_id, request_type,
        operation_code, target_vendor_code,
        None, False, None, None, None, None, None, None, err,
    )
    _log_ai_execute_completed(
        status_code,
        request_type=request_type,
        operation_code=operation_code,
        target_vendor_code=target_vendor_code,
        transaction_id=transaction_id,
        correlation_id=correlation_id,
        error_code=code,
        error_category=category,
    )
    return add_cors_to_response({
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload, default=str),
    })


def _canonical_error_to_ai_envelope(
    canonical_resp: dict[str, Any],
    request_type: str = "DATA",
    operation_code: str | None = None,
    target_vendor_code: str | None = None,
) -> dict[str, Any]:
    """Convert canonical_error response to AI envelope format. Always use AI envelope."""
    try:
        body = json.loads(canonical_resp.get("body", "{}"))
    except (json.JSONDecodeError, TypeError):
        body = {}
    transaction_id = body.get("transactionId") or str(uuid.uuid4())
    correlation_id = body.get("correlationId") or str(uuid.uuid4())
    err = body.get("error", {})
    payload = _build_response_envelope(
        transaction_id, correlation_id, request_type,
        operation_code, target_vendor_code,
        None, False, None, None, None, None, None, None, err,
    )
    status_code = canonical_resp.get("statusCode", 400)
    _log_ai_execute_completed(
        status_code,
        request_type=request_type,
        operation_code=operation_code,
        target_vendor_code=target_vendor_code,
        transaction_id=transaction_id,
        correlation_id=correlation_id,
        error_code=err.get("code"),
        error_category=err.get("category"),
    )
    return add_cors_to_response({
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload, default=str),
    })


def _handle_prompt_request(body: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    """Handle PROMPT: invoke Bedrock Agent, return reply as finalText."""
    transaction_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    prompt = (body.get("prompt") or "").strip()

    log_json("INFO", "ai_execute_prompt_start", requestType="PROMPT", correlationId=correlation_id)

    try:
        agent_reply = _invoke_bedrock_agent(prompt)
    except Exception as e:
        log_json("ERROR", "ai_execute_prompt_failed", correlationId=correlation_id, error=str(e))
        err = {
            "code": "AGENT_INVOKE_ERROR",
            "message": str(e)[:500],
            "category": "PLATFORM",
            "retryable": True,
        }
        payload = _build_response_envelope(
            transaction_id, correlation_id, "PROMPT", None, None,
            None, False, None, None, AIFormatterReason.PROMPT_MODE, None, None, None, err,
        )
        _log_ai_execute_completed(
            502, request_type="PROMPT", transaction_id=transaction_id, correlation_id=correlation_id,
            error_code="AGENT_INVOKE_ERROR", error_category="PLATFORM",
        )
        return add_cors_to_response({
            "statusCode": 502,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(payload, default=str),
        })

    log_json("INFO", "ai_execute_prompt_ok", correlationId=correlation_id, replyLen=len(agent_reply or ""))


    payload = _build_response_envelope(
        transaction_id,
        correlation_id,
        "PROMPT",
        None,
        None,
        None,
        False,
        None,
        None,
        AIFormatterReason.PROMPT_MODE,
        None,
        None,
        agent_reply,
        None,
    )
    _log_ai_execute_completed(200, request_type="PROMPT", transaction_id=transaction_id, correlation_id=correlation_id)
    return add_cors_to_response({
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload, default=str),
    })


def _handle_data_request(body: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    """Handle DATA: call Runtime /v1/execute, optionally apply AI formatter."""
    transaction_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    operation_code = (body.get("operationCode") or "").strip()
    target_vendor = (body.get("targetVendorCode") or "").strip()
    source_vendor_body = (body.get("sourceVendorCode") or body.get("sourceVendor") or "").strip()
    source_vendor_auth = (ctx.get("source_vendor_from_auth") or "").strip()
    source_vendor = source_vendor_auth
    payload = body.get("payload") or {}
    idempotency_key = (body.get("idempotencyKey") or "").strip() or None

    source_vendor_policy = evaluate_policy({
        "policy": "AI_GATEWAY_SOURCE_VENDOR_REQUIRED",
        "check": lambda: source_vendor_auth != "",
        "deny_reason": "JWT vendor identity is missing required bcpAuth claim",
        "details": {
            "operationCode": operation_code,
            "targetVendorCode": target_vendor,
        },
    })
    if not source_vendor_policy.get("allowed", False):
        err = {
            "code": "AUTH_ERROR",
            "message": str(source_vendor_policy.get("reason") or "JWT vendor identity is missing required bcpAuth claim"),
            "category": "AUTH",
            "retryable": False,
        }
        payload_out = _build_response_envelope(
            transaction_id, correlation_id, "DATA", operation_code, target_vendor,
            None, False, None, None, None, None, None, None, err,
        )
        return add_cors_to_response({
            "statusCode": 401,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(payload_out, default=str),
        })

    spoof_policy = evaluate_policy({
        "policy": "AI_GATEWAY_VENDOR_SPOOF",
        "check": lambda: (not source_vendor_body) or (source_vendor_auth == source_vendor_body),
        "deny_reason": "sourceVendor/sourceVendorCode does not match token bcpAuth",
        "details": {
            "sourceVendorBody": source_vendor_body or None,
            "sourceVendorAuth": source_vendor_auth or None,
        },
    })
    if not spoof_policy.get("allowed", False):
        err = {
            "code": "VENDOR_SPOOF_BLOCKED",
            "message": str(spoof_policy.get("reason") or "sourceVendor/sourceVendorCode does not match token bcpAuth"),
            "category": "AUTH",
            "retryable": False,
        }
        payload_out = _build_response_envelope(
            transaction_id, correlation_id, "DATA", operation_code, target_vendor,
            None, False, None, None, None, None, None, None, err,
        )
        return add_cors_to_response({
            "statusCode": 403,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(payload_out, default=str),
        })

    # Runtime execute requires sourceVendor for allowlist checks.
    use_runtime = bool((os.environ.get("RUNTIME_API_URL") or "").strip())
    runtime_source_policy = evaluate_policy({
        "policy": "AI_GATEWAY_RUNTIME_SOURCE_VENDOR",
        "check": lambda: (not use_runtime) or bool(source_vendor),
        "deny_reason": "JWT vendor claim (bcpAuth) is required for Runtime API execute",
    })
    if not runtime_source_policy.get("allowed", False):
        err = {"code": "AUTH_ERROR", "message": "JWT vendor claim (bcpAuth) is required for Runtime API execute", "category": "AUTH", "retryable": False}
        payload_out = _build_response_envelope(
            transaction_id, correlation_id, "DATA", operation_code, target_vendor,
            None, False, None, None, None, None, None, None, err,
        )
        _log_ai_execute_completed(401, request_type="DATA", operation_code=operation_code, target_vendor_code=target_vendor, transaction_id=transaction_id, correlation_id=correlation_id, error_code="AUTH_ERROR", error_category="AUTH")
        return add_cors_to_response({
            "statusCode": 401,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(payload_out, default=str),
        })

    log_json(
        "INFO", "ai_execute_data_start",
        requestType="DATA", operationCode=operation_code, targetVendorCode=target_vendor,
        correlationId=correlation_id, channel=body.get("channel"),
    )

    # Load operation AI config
    op_cfg = _load_operation_ai_config(operation_code)
    if op_cfg is None:
        err = {"code": "OPERATION_NOT_FOUND", "message": "Operation not found or inactive", "category": "NOT_FOUND", "retryable": False}
        payload_out = _build_response_envelope(
            transaction_id, correlation_id, "DATA", operation_code, target_vendor,
            None, False, None, None, None, None, None, None, err,
        )
        _log_ai_execute_completed(404, request_type="DATA", operation_code=operation_code, target_vendor_code=target_vendor, transaction_id=transaction_id, correlation_id=correlation_id, error_code="OPERATION_NOT_FOUND", error_category="NOT_FOUND")
        return add_cors_to_response({
            "statusCode": 404,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(payload_out, default=str),
        })

    # Call Integration Hub via Runtime API (/v1/execute) only.
    base_url = (os.environ.get("VENDOR_API_URL") or os.environ.get("INTEGRATION_HUB_API_URL") or "").strip()
    use_runtime_api = bool((os.environ.get("RUNTIME_API_URL") or "").strip())
    try:
        hub_response = _call_integration_api(
            target_vendor, operation_code, payload, idempotency_key, ctx.get("auth_header"), base_url or "",
            source_vendor=source_vendor or None,
            use_runtime_api=use_runtime_api,
        )
    except RuntimeError as e:
        err = {"code": "CONFIGURATION_ERROR", "message": str(e)[:500], "category": "PLATFORM", "retryable": False}
        payload_out = _build_response_envelope(
            transaction_id, correlation_id, "DATA", operation_code, target_vendor,
            None, False, None, None, None, None, None, None, err,
        )
        _log_ai_execute_completed(500, request_type="DATA", operation_code=operation_code, target_vendor_code=target_vendor, transaction_id=transaction_id, correlation_id=correlation_id, error_code="CONFIGURATION_ERROR", error_category="PLATFORM")
        return add_cors_to_response({
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(payload_out, default=str),
        })
    except urllib.error.HTTPError as e:
        hub_body = ""
        try:
            hub_body = e.read().decode() if getattr(e, "fp", None) else ""
        except Exception:
            pass
        hub_json: dict[str, Any] = {}
        try:
            hub_json = json.loads(hub_body) if hub_body else {}
        except json.JSONDecodeError:
            pass
        err_obj = (hub_json or {}).get("error", {}) or {}
        err = {
            "code": err_obj.get("code", "INTEGRATION_API_ERROR"),
            "message": err_obj.get("message", str(e))[:500],
            "category": err_obj.get("category", "DOWNSTREAM"),
            "retryable": err_obj.get("retryable", False),
        }
        log_json("WARN", "ai_execute_data_hub_error", correlationId=correlation_id, status=e.code, error=err.get("message"))
        # rawResult = full hub error JSON (or None if unparseable)
        raw_result_err = hub_json if hub_json else None
        payload_out = _build_response_envelope(
            transaction_id, correlation_id, "DATA", operation_code, target_vendor,
            raw_result_err,
            False, None, None, None, None, None, None, err,
        )
        sc = min(e.code, 599)
        _log_ai_execute_completed(sc, request_type="DATA", operation_code=operation_code, target_vendor_code=target_vendor, channel=body.get("channel"), transaction_id=transaction_id, correlation_id=correlation_id, error_code=err.get("code"), error_category=err.get("category", "DOWNSTREAM"))
        return add_cors_to_response({
            "statusCode": sc,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(payload_out, default=str),
        })
    except urllib.error.URLError as e:
        err = {"code": "INTEGRATION_API_UNREACHABLE", "message": str(e.reason or str(e))[:500], "category": "DOWNSTREAM", "retryable": True}
        log_json("WARN", "ai_execute_data_hub_unreachable", correlationId=correlation_id, error=str(e))
        payload_out = _build_response_envelope(
            transaction_id, correlation_id, "DATA", operation_code, target_vendor,
            None, False, None, None, None, None, None, None, err,
        )
        _log_ai_execute_completed(502, request_type="DATA", operation_code=operation_code, target_vendor_code=target_vendor, channel=body.get("channel"), transaction_id=transaction_id, correlation_id=correlation_id, error_code="INTEGRATION_API_UNREACHABLE", error_category="DOWNSTREAM")
        return add_cors_to_response({
            "statusCode": 502,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(payload_out, default=str),
        })
    except Exception as e:
        err = {"code": "INTERNAL_ERROR", "message": str(e)[:500], "category": "PLATFORM", "retryable": False}
        log_json("ERROR", "ai_execute_data_hub_exception", correlationId=correlation_id, error=str(e))
        payload_out = _build_response_envelope(
            transaction_id, correlation_id, "DATA", operation_code, target_vendor,
            None, False, None, None, None, None, None, None, err,
        )
        _log_ai_execute_completed(500, request_type="DATA", operation_code=operation_code, target_vendor_code=target_vendor, channel=body.get("channel"), transaction_id=transaction_id, correlation_id=correlation_id, error_code="INTERNAL_ERROR", error_category="PLATFORM")
        return add_cors_to_response({
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(payload_out, default=str),
        })

    # Runtime success - extract canonical/raw result.
    raw_result = hub_response
    tx_id = hub_response.get("transactionId") or transaction_id
    corr_id = hub_response.get("correlationId") or correlation_id
    response_body = hub_response.get("responseBody") if isinstance(hub_response, dict) else None
    formatter_input = response_body if response_body is not None else hub_response

    log_json("INFO", "ai_execute_data_hub_ok", transactionId=tx_id, correlationId=corr_id)

    feature_enabled = _is_ai_feature_enabled(source_vendor_auth)
    decision: FormatterDecision = decide_formatter_action(
        request_type="DATA",
        global_gate_enabled=feature_enabled,
        operation_mode=op_cfg.get("ai_presentation_mode"),
        request_flag=body.get("aiFormatter") if isinstance(body.get("aiFormatter"), bool) else False,
    )
    if not decision.should_call:
        payload_out = _build_response_envelope(
            tx_id,
            corr_id,
            "DATA",
            operation_code,
            target_vendor,
            raw_result,
            False,
            decision.mode,
            None,
            decision.reason,
            None,
            None,
            None,
            None,
        )
        _log_ai_execute_completed(
            200,
            request_type="DATA",
            operation_code=operation_code,
            target_vendor_code=target_vendor,
            channel=body.get("channel"),
            transaction_id=tx_id,
            correlation_id=corr_id,
            ai_formatter_applied=False,
            ai_formatter_mode=decision.mode,
            ai_formatter_model=None,
        )
        return add_cors_to_response({
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(payload_out, default=str),
        })

    formatted_text: str | None = None
    formatter_error: str | None = None
    model_id = op_cfg.get("ai_formatter_model") or os.environ.get("AI_FORMATTER_MODEL")
    timeout_ms = max(250, int(os.environ.get("AI_FORMATTER_TIMEOUT_MS", "3500")))
    use_bedrock = (os.environ.get("USE_BEDROCK", "true")).strip().lower() not in ("false", "0")

    try:
        if not use_bedrock:
            formatted_text = build_local_stub_summary(formatter_input, max_chars=_FORMATTER_OUTPUT_MAX_CHARS)
        else:
            safe_json = json.dumps(formatter_input, default=str)
            if len(safe_json) > _PROMPT_MODEL_MAX_CHARS:
                safe_json = safe_json[:_PROMPT_MODEL_MAX_CHARS] + "... [truncated]"
            user_prompt = (
                f"Operation: {operation_code}\n"
                f"TargetVendor: {target_vendor}\n"
                f"Create a concise plain-text summary for this JSON response.\n\n"
                f"{safe_json}"
            )
            system_prompt = "You are a concise formatter. Output plain text only, no markdown."
            bedrock_region = (os.environ.get("BEDROCK_REGION") or os.environ.get("AWS_REGION") or "").strip() or None
            formatted_text = call_formatter_model(
                model_id or "",
                system_prompt,
                user_prompt,
                region_name=bedrock_region,
            )
            if formatted_text and len(formatted_text) > _FORMATTER_OUTPUT_MAX_CHARS:
                formatted_text = formatted_text[:_FORMATTER_OUTPUT_MAX_CHARS] + "... [truncated]"
        log_json(
            "INFO", "ai_formatter_ok",
            operationCode=operation_code, transactionId=tx_id,
            applied=True, mode=decision.mode, model=model_id,
            timeoutMs=timeout_ms,
            formattedPreview=(formatted_text or "")[:200],
        )
    except FormatterError as e:
        formatter_error = str(e)[:500]
        log_json(
            "WARN", "ai_formatter_failed",
            transactionId=tx_id, correlationId=corr_id,
            operationCode=operation_code, targetVendorCode=target_vendor,
            model_id=model_id, error=str(e),
            timeoutMs=timeout_ms,
        )

    applied = bool(formatted_text)
    raw_for_response: dict[str, Any] | None = raw_result
    ai_reason = AIFormatterReason.APPLIED if applied else AIFormatterReason.FORMATTER_ERROR
    final_text = formatted_text if applied else None
    payload_out = _build_response_envelope(
        tx_id, corr_id, "DATA", operation_code, target_vendor,
        raw_for_response, applied, decision.mode, model_id if applied else None,
        ai_reason, formatter_error,
        formatted_text, final_text, None,
    )
    _log_ai_execute_completed(
        200, request_type="DATA", operation_code=operation_code, target_vendor_code=target_vendor,
        channel=body.get("channel"), transaction_id=tx_id, correlation_id=corr_id,
        ai_formatter_applied=applied, ai_formatter_mode=decision.mode, ai_formatter_model=model_id if applied else None,
        formatted_preview=formatted_text if formatted_text else None,
    )
    return add_cors_to_response({
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload_out, default=str),
    })


def _handler_impl(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Handle POST /v1/ai/execute. All responses use AI envelope (rawResult, aiFormatter, finalText, error)."""
    if os.environ.get("AI_ENDPOINT_ENABLED", "true").lower() in ("false", "0"):
        return _ai_envelope_error_response(
            "SERVICE_DISABLED", "AI endpoint is disabled", 503,
            request_type="DATA", category="PLATFORM", retryable=False,
        )

    request_scope = (os.environ.get("AI_EXECUTE_SCOPE") or "").strip() or None
    auth_err, auth_claims = _require_ai_gateway_auth(event, request_scope)
    if auth_err:
        log_json("WARN", "ai_execute_auth_failed")
        return _canonical_error_to_ai_envelope(auth_err, request_type="DATA")

    # Parse body
    raw_body = event.get("body") or ""
    if isinstance(raw_body, str):
        try:
            body = json.loads(raw_body) if raw_body.strip() else {}
        except json.JSONDecodeError:
            return _ai_envelope_error_response(
                "VALIDATION_ERROR", "Request body must be valid JSON", 400,
                request_type="DATA", category="VALIDATION", retryable=False,
            )
    else:
        body = raw_body if isinstance(raw_body, dict) else {}

    if not isinstance(body, dict):
        return _ai_envelope_error_response(
            "VALIDATION_ERROR", "Request body must be a JSON object", 400,
            request_type="DATA", category="VALIDATION", retryable=False,
        )

    # Size limit
    body_bytes = len(json.dumps(body).encode("utf-8"))
    if body_bytes > _MAX_BODY_BYTES:
        return _ai_envelope_error_response(
            "VALIDATION_ERROR",
            f"Request body exceeds max size ({_MAX_BODY_BYTES} bytes)",
            400,
            request_type=(body.get("requestType") or "DATA"),
            operation_code=body.get("operationCode"),
            target_vendor_code=body.get("targetVendorCode"),
            category="VALIDATION",
            retryable=False,
            details={"maxBytes": _MAX_BODY_BYTES},
        )

    validation_err = _validate_request_body(body)
    if validation_err:
        return _ai_envelope_error_response(
            "VALIDATION_ERROR", validation_err, 400,
            request_type=(body.get("requestType") or "DATA"),
            operation_code=body.get("operationCode"),
            target_vendor_code=body.get("targetVendorCode"),
            category="VALIDATION",
            retryable=False,
        )

    ctx = get_context(event, context)
    ctx["auth_method"] = "bcpAuth"
    ctx["source_vendor_from_auth"] = str((auth_claims or {}).get("bcpAuth") or "").strip().upper()
    headers = {k.lower(): (v if isinstance(v, str) else str(v)) for k, v in (event.get("headers") or {}).items()}
    ctx["auth_header"] = (headers.get("authorization") or "").strip() or None

    request_type = (body.get("requestType") or "").upper()
    if request_type == "PROMPT":
        return _handle_prompt_request(body, ctx)
    return _handle_data_request(body, ctx)


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Lambda entry point."""
    return with_observability(_handler_impl, "ai_gateway")(event, context)
