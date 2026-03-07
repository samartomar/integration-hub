"""Internal AI Gateway invoker - for registry/vendor-registry to request debugger enrichment.

Performs lambda:InvokeFunction to AI Gateway Lambda. No Bedrock calls here.
Used by integration_debugger when enhance_with_ai=True.
"""

from __future__ import annotations

import json
import os
from typing import Any


def invoke_debugger_enrich(report: dict[str, Any]) -> dict[str, Any] | None:
    """
    Invoke AI Gateway Lambda with action=debugger_enrich.

    Sends only redacted deterministic report. Returns enrichment object or None on failure.
    On timeout/error: returns None; caller adds fallback aiWarnings.
    """
    import boto3

    fn_arn = (os.environ.get("AI_GATEWAY_FUNCTION_ARN") or "").strip()
    fn_name = (os.environ.get("AI_GATEWAY_FUNCTION_NAME") or "").strip()
    if not fn_arn and not fn_name:
        return None

    payload: dict[str, Any] = {
        "action": "debugger_enrich",
        "report": report,
    }
    payload_bytes = json.dumps(payload).encode("utf-8")
    timeout_sec = min(15, max(2, int(os.environ.get("AI_GATEWAY_DEBUGGER_TIMEOUT_SEC", "10"))))

    try:
        client = boto3.client("lambda")
        invoke_kw: dict[str, Any] = {
            "FunctionName": fn_arn or fn_name,
            "InvocationType": "RequestResponse",
            "Payload": payload_bytes,
        }
        response = client.invoke(**invoke_kw)
    except Exception:
        return None

    status = response.get("StatusCode", 0)
    if status != 200:
        return None

    raw = response.get("Payload")
    if raw is None:
        return None

    try:
        body = raw.read().decode("utf-8")
        result = json.loads(body) if body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    if not isinstance(result, dict):
        return None
    if result.get("enrichment"):
        return result["enrichment"]
    if "aiWarnings" in result or "modelInfo" in result:
        return result
    return None


def invoke_mapping_suggest(context: dict[str, Any]) -> dict[str, Any] | None:
    """
    Invoke AI Gateway Lambda with action=mapping_suggest.

    Sends redacted mapping context. Returns suggestion dict or None on failure.
    On timeout/error: returns None; caller adds fallback.
    """
    import boto3

    fn_arn = (os.environ.get("AI_GATEWAY_FUNCTION_ARN") or "").strip()
    fn_name = (os.environ.get("AI_GATEWAY_FUNCTION_NAME") or "").strip()
    if not fn_arn and not fn_name:
        return None

    payload: dict[str, Any] = {
        "action": "mapping_suggest",
        "payload": context,
    }
    payload_bytes = json.dumps(payload).encode("utf-8")
    timeout_sec = min(15, max(2, int(os.environ.get("AI_GATEWAY_MAPPING_SUGGEST_TIMEOUT_SEC", "10"))))

    try:
        client = boto3.client("lambda")
        invoke_kw: dict[str, Any] = {
            "FunctionName": fn_arn or fn_name,
            "InvocationType": "RequestResponse",
            "Payload": payload_bytes,
        }
        response = client.invoke(**invoke_kw)
    except Exception:
        return None

    status = response.get("StatusCode", 0)
    if status != 200:
        return None

    raw = response.get("Payload")
    if raw is None:
        return None

    try:
        body = raw.read().decode("utf-8")
        result = json.loads(body) if body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    if not isinstance(result, dict):
        return None
    if result.get("suggestion"):
        return result["suggestion"]
    if "proposedFieldMappings" in result or "summary" in result:
        return result
    if "warnings" in result or "modelInfo" in result:
        return result
    return None
