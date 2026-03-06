"""Canonical runtime bridge - bridge canonical requests into the existing execute path.

Runs preflight first. Supports DRY_RUN (preview only) and EXECUTE (calls existing
routing handler internally). No parallel runtime engine. No internal HTTP.
"""

from __future__ import annotations

from typing import Any, Callable

from schema.canonical_registry import resolve_version
from schema.canonical_runtime_preflight import run_canonical_preflight

BRIDGE_NOTES = [
    "Bridge uses the existing execute path.",
    "No parallel runtime logic was introduced.",
]

ALLOWED_MODES = frozenset({"DRY_RUN", "EXECUTE"})


def validate_bridge_request(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate bridge request shape. Returns list of errors (empty if valid)."""
    errors: list[dict[str, Any]] = []

    if not isinstance(payload, dict):
        return [{"field": "body", "message": "Request body must be a JSON object."}]

    source = (payload.get("sourceVendor") or payload.get("source_vendor") or "").strip()
    target = (payload.get("targetVendor") or payload.get("target_vendor") or "").strip()
    mode = (payload.get("mode") or "").strip().upper()
    envelope = payload.get("envelope")

    if not source:
        errors.append({"field": "sourceVendor", "message": "sourceVendor is required and must be non-empty."})
    if not target:
        errors.append({"field": "targetVendor", "message": "targetVendor is required and must be non-empty."})
    if not mode:
        errors.append({"field": "mode", "message": "mode is required."})
    elif mode not in ALLOWED_MODES:
        errors.append({"field": "mode", "message": f"mode must be one of: DRY_RUN, EXECUTE. Got: {mode}"})
    if envelope is None:
        errors.append({"field": "envelope", "message": "envelope is required."})
    elif not isinstance(envelope, dict):
        errors.append({"field": "envelope", "message": "envelope must be a JSON object."})

    return errors


def build_execute_request_from_canonical(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Build the exact internal request shape expected by the current execute path.

    Maps canonical envelope to: targetVendor, operation, parameters, idempotencyKey.
    Returns None if validation fails.
    """
    errors = validate_bridge_request(payload)
    if errors:
        return None

    source = (payload.get("sourceVendor") or payload.get("source_vendor") or "").strip()
    target = (payload.get("targetVendor") or payload.get("target_vendor") or "").strip()
    envelope = payload.get("envelope") or {}
    op_code = (envelope.get("operationCode") or envelope.get("operation_code") or "").strip().upper()
    version_in = (envelope.get("version") or "").strip()
    direction = (envelope.get("direction") or "").strip().upper()
    payload_data = envelope.get("payload")
    correlation_id = envelope.get("correlationId") or envelope.get("correlation_id")

    if direction != "REQUEST":
        return None
    if not op_code:
        return None

    resolved = resolve_version(op_code, version_in or None)
    if resolved is None:
        return None

    parameters = payload_data if isinstance(payload_data, dict) else {}

    result: dict[str, Any] = {
        "targetVendor": target,
        "operation": op_code,
        "parameters": parameters,
    }
    if correlation_id and isinstance(correlation_id, str) and correlation_id.strip():
        result["idempotencyKey"] = correlation_id.strip()

    return result


def run_canonical_bridge(
    payload: dict[str, Any],
    *,
    executor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    allowlist_ok: bool | None = None,
    mapping_ok: bool | None = None,
) -> dict[str, Any]:
    """Run canonical bridge: preflight first, then DRY_RUN or EXECUTE.

    Args:
        payload: Bridge request with sourceVendor, targetVendor, mode, envelope.
        executor: Callable that invokes the existing execute path. Required for EXECUTE mode.
        allowlist_ok: Optional. Passed to preflight for VENDOR_PAIR_ALLOWED check.
        mapping_ok: Optional. Passed to preflight for RUNTIME_MAPPING_FOUND check.

    Returns:
        Bridge result with status, preflight, executeRequestPreview, executeResult (if EXECUTE).
    """
    errors = validate_bridge_request(payload)
    if errors:
        return {
            "mode": (payload.get("mode") or "").strip().upper() or "DRY_RUN",
            "valid": False,
            "status": "BLOCKED",
            "operationCode": "",
            "canonicalVersion": "",
            "sourceVendor": (payload.get("sourceVendor") or "").strip(),
            "targetVendor": (payload.get("targetVendor") or "").strip(),
            "errors": errors,
            "notes": BRIDGE_NOTES,
        }

    source = (payload.get("sourceVendor") or payload.get("source_vendor") or "").strip()
    target = (payload.get("targetVendor") or payload.get("target_vendor") or "").strip()
    mode = (payload.get("mode") or "").strip().upper()
    envelope = payload.get("envelope") or {}

    # Run preflight first
    preflight_payload = {"sourceVendor": source, "targetVendor": target, "envelope": envelope}
    preflight = run_canonical_preflight(preflight_payload, allowlist_ok=allowlist_ok, mapping_ok=mapping_ok)

    op_code = preflight.get("operationCode") or ""
    canonical_version = preflight.get("canonicalVersion") or ""
    normalized_envelope = preflight.get("normalizedEnvelope")
    preflight_valid = preflight.get("valid", False)
    preflight_status = preflight.get("status", "BLOCKED")

    # Build execute request preview (same shape the routing handler expects)
    execute_request = build_execute_request_from_canonical(payload)
    execute_request_preview = execute_request if execute_request else {}

    # If preflight blocks, do not execute
    if not preflight_valid or preflight_status == "BLOCKED":
        return {
            "mode": mode,
            "valid": False,
            "status": "BLOCKED",
            "operationCode": op_code,
            "canonicalVersion": canonical_version,
            "sourceVendor": source,
            "targetVendor": target,
            "normalizedEnvelope": normalized_envelope,
            "preflight": preflight,
            "executeRequestPreview": execute_request_preview,
            "executionPlan": {
                "canExecute": False,
                "reason": "Preflight blocked. Fix checks before execution.",
            },
            "notes": BRIDGE_NOTES,
        }

    # DRY_RUN: return preview only
    if mode == "DRY_RUN":
        return {
            "mode": mode,
            "valid": True,
            "status": "READY",
            "operationCode": op_code,
            "canonicalVersion": canonical_version,
            "sourceVendor": source,
            "targetVendor": target,
            "normalizedEnvelope": normalized_envelope,
            "preflight": preflight,
            "executeRequestPreview": execute_request_preview,
            "executionPlan": {
                "canExecute": True,
                "reason": "Preflight passed. Use EXECUTE mode to run via existing runtime path.",
            },
            "notes": BRIDGE_NOTES,
        }

    # EXECUTE: call existing execute path via executor
    if mode == "EXECUTE":
        if not executor:
            return {
                "mode": mode,
                "valid": False,
                "status": "FAILED",
                "operationCode": op_code,
                "canonicalVersion": canonical_version,
                "sourceVendor": source,
                "targetVendor": target,
                "normalizedEnvelope": normalized_envelope,
                "preflight": preflight,
                "executeRequestPreview": execute_request_preview,
                "executeResult": {
                    "error": "Executor not provided. Bridge cannot invoke execute path.",
                },
                "notes": BRIDGE_NOTES,
            }

        try:
            execute_response = executor(execute_request_preview)
            return {
                "mode": mode,
                "valid": execute_response.get("statusCode", 500) < 400,
                "status": "EXECUTED" if execute_response.get("statusCode", 500) < 400 else "FAILED",
                "operationCode": op_code,
                "canonicalVersion": canonical_version,
                "sourceVendor": source,
                "targetVendor": target,
                "normalizedEnvelope": normalized_envelope,
                "preflight": preflight,
                "executeRequestPreview": execute_request_preview,
                "executeResult": _summarize_execute_response(execute_response),
                "notes": BRIDGE_NOTES,
            }
        except Exception as e:
            return {
                "mode": mode,
                "valid": False,
                "status": "FAILED",
                "operationCode": op_code,
                "canonicalVersion": canonical_version,
                "sourceVendor": source,
                "targetVendor": target,
                "normalizedEnvelope": normalized_envelope,
                "preflight": preflight,
                "executeRequestPreview": execute_request_preview,
                "executeResult": {
                    "error": str(e),
                    "errorType": type(e).__name__,
                },
                "notes": BRIDGE_NOTES,
            }

    return {
        "mode": mode,
        "valid": False,
        "status": "BLOCKED",
        "operationCode": op_code,
        "canonicalVersion": canonical_version,
        "sourceVendor": source,
        "targetVendor": target,
        "normalizedEnvelope": normalized_envelope,
        "preflight": preflight,
        "executeRequestPreview": execute_request_preview,
        "notes": BRIDGE_NOTES,
    }


def _summarize_execute_response(response: dict[str, Any]) -> dict[str, Any]:
    """Extract summary from routing handler response (statusCode, body)."""
    status_code = response.get("statusCode", 500)
    body = response.get("body")
    if isinstance(body, str):
        try:
            import json
            body = json.loads(body)
        except Exception:
            body = {"raw": body[:1024] if body else ""}
    return {
        "statusCode": status_code,
        "body": body,
    }
