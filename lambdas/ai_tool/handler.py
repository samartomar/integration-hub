"""AI Tool Lambda - ExecuteIntegration and ListOperations. Routes to appropriate handler."""

from __future__ import annotations

import json
import urllib.error
from typing import Any

from config import get_integration_hub_api_url
from envelope import build_canonical_envelope, generate_idempotency_key_if_missing
from integration_api import call_integration_api
from observability import get_context, log_json, with_observability
from registry_client import fetch_operations
from response import error, needs_input, success, unknown_operation
from timeout import ensure_sufficient_time
from validation import (
    ValidationError,
    fetch_request_schema,
    get_operation_canonical_version,
    validate_allowlist,
    validate_input_schema,
    validate_operation_exists_and_active,
    validate_parameters_schema,
    validate_vendor_exists_and_active,
)


def _parse_input(event: dict[str, Any]) -> dict[str, Any]:
    """Parse input from API Gateway proxy, Bedrock action group, or direct Lambda invoke."""
    raw = event.get("body") or event.get("input") or event.get("requestBody") or event
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    if not isinstance(raw, dict):
        return {}
    # Flatten Bedrock parameters array [{name, value}, ...] into body
    params = raw.get("parameters") or raw.get("parameter") or []
    if isinstance(params, list):
        for p in params:
            if isinstance(p, dict) and "name" in p and "value" in p:
                raw = {**raw, p["name"]: p["value"]}
    return raw


def _handle_list_operations(body: dict[str, Any]) -> dict[str, Any]:
    """Handle ListOperations tool: fetch operations from Registry API."""
    try:
        get_integration_hub_api_url()
    except ValueError as e:
        return error(500, "CONFIGURATION_ERROR", str(e))
    is_active = body.get("isActive", True)
    if isinstance(is_active, str):
        is_active = is_active.lower() in ("true", "1", "yes")
    source = (body.get("sourceVendor") or "").strip() or None
    target = (body.get("targetVendor") or "").strip() or None
    if (source and not target) or (target and not source):
        return error(400, "VALIDATION_ERROR", "sourceVendor and targetVendor must both be provided or both omitted")
    ops = fetch_operations(is_active=is_active, source_vendor=source, target_vendor=target)
    # ListOperations uses same structured format; executeResult contains operations list
    return success({"operations": ops})


def _handler_impl(event: dict[str, Any], context: object) -> dict[str, Any]:
    """
    AI Tool Lambda handler. Exposes ExecuteIntegration and ListOperations.

    Routes by input: operationCode/operation -> ExecuteIntegration; else -> ListOperations.
    """
    body = _parse_input(event)
    if body is None:
        return error(400, "INVALID_INPUT", "Request body or input is required")

    # Route: ListOperations if no operation/operationCode; else ExecuteIntegration
    if not (body.get("operation") or body.get("operationCode")):
        return _handle_list_operations(body)

    try:
        get_integration_hub_api_url()
    except ValueError as e:
        return error(500, "CONFIGURATION_ERROR", str(e))

    try:
        validated = validate_input_schema(body)
    except ValidationError as e:
        ctx = get_context(event, context)
        log_json("WARN", "validation_failed", ctx=ctx, error=str(e))
        # Missing/invalid top-level fields -> NEEDS_INPUT for Bedrock to ask user
        missing: list[str] = []
        if not (body.get("sourceVendor") or "").strip():
            missing.append("sourceVendor")
        if not (body.get("targetVendor") or "").strip():
            missing.append("targetVendor")
        op = body.get("operation") or body.get("operationCode") or ""
        if not (op if isinstance(op, str) else "").strip():
            missing.append("operation")
        if body.get("parameters") is None:
            missing.append("parameters")
        return needs_input(
            message=e.message,
            violations=[{"path": "root", "message": e.message}],
            required=missing if missing else ["sourceVendor", "targetVendor", "operation", "parameters"],
        )

    source_vendor = validated["source_vendor"]
    target_vendor = validated["target_vendor"]
    operation = validated["operation"]
    parameters = validated["parameters"]
    idempotency_key = generate_idempotency_key_if_missing(validated["idempotency_key"])

    try:
        validate_vendor_exists_and_active(source_vendor)
    except ValidationError as e:
        return error(404, e.code, e.message)

    try:
        validate_vendor_exists_and_active(target_vendor)
    except ValidationError as e:
        return error(404, e.code, e.message)

    try:
        validate_operation_exists_and_active(operation)
    except ValidationError as e:
        return error(404, e.code, e.message)

    try:
        validate_allowlist(source_vendor, target_vendor, operation)
    except ValidationError as e:
        ctx = get_context(event, context)
        log_json("WARN", "allowlist_denied", ctx=ctx, error=str(e))
        return error(403, e.code, e.message)

    # Fetch contract from DB (canonical_version from control_plane.operations)
    canonical_version = get_operation_canonical_version(operation)
    request_schema = fetch_request_schema(operation, canonical_version)
    if request_schema is None:
        return unknown_operation(operation)

    violations, required = validate_parameters_schema(parameters, request_schema)
    if violations:
        ctx = get_context(event, context)
        log_json("WARN", "validation_failed", ctx=ctx, decision="parameters_schema", violations=violations)
        return needs_input(
            message="Missing or invalid parameters",
            violations=violations,
            required=required,
        )

    envelope = build_canonical_envelope(
        source_vendor, target_vendor, operation, idempotency_key, parameters
    )

    try:
        ensure_sufficient_time(context)
        response_body = call_integration_api(envelope)
        return success(response_body)
    except TimeoutError as e:
        return error(504, "TIMEOUT", str(e))
    except urllib.error.HTTPError as e:
        api_error_code = "INTEGRATION_API_ERROR"
        hub_message = str(e)
        details: dict[str, Any] = {}
        try:
            err_body = e.read().decode() if getattr(e, "fp", None) else ""
            if err_body:
                err_json = json.loads(err_body)
                err_obj = err_json.get("error") if isinstance(err_json, dict) else None
                hub_violations = None
                if isinstance(err_obj, dict):
                    api_error_code = err_obj.get("code") or api_error_code
                    hub_message = err_obj.get("message") or hub_message
                    if err_obj.get("details"):
                        details = dict(err_obj.get("details"))
                    if err_obj.get("violations") is not None:
                        hub_violations = err_obj["violations"]
                return error(
                    e.code, api_error_code, hub_message,
                    details=details if details else None,
                    violations=hub_violations,
                )
        except (json.JSONDecodeError, AttributeError, ValueError):
            details = {"raw": str(e)[:500]}
        return error(e.code, api_error_code, hub_message, details=details if details else None)
    except urllib.error.URLError as e:
        return error(502, "INTEGRATION_API_UNREACHABLE", f"Integration API unreachable: {e.reason}")
    except Exception as e:
        return error(500, "INTERNAL_ERROR", str(e), details={"type": type(e).__name__})


handler = with_observability(_handler_impl, "ai_tool")
