"""Shared Syntegris feature handlers - thin transport layer over schema/ai services.

Used by both admin (registry_lambda) and partner (vendor_registry_lambda) endpoints.
No auth assumptions; caller injects vendor identity and enforces scoping.
"""

from __future__ import annotations

from typing import Any, Callable


def list_canonical_operations() -> list[dict[str, Any]]:
    """List canonical operations from schema registry."""
    from schema.canonical_registry import list_operations

    return list_operations()


def get_canonical_operation(operation_code: str, version: str | None = None) -> dict[str, Any] | None:
    """Get canonical operation detail with schemas and examples."""
    from schema.canonical_registry import get_operation

    return get_operation(operation_code, version)


def validate_sandbox_request(body: dict[str, Any]) -> dict[str, Any]:
    """Validate request payload against canonical schema. Returns {valid, errors?, normalizedVersion?}."""
    from schema.canonical_registry import resolve_version
    from schema.sandbox_runner import validate_sandbox_request as _validate

    operation_code = (body.get("operationCode") or body.get("operation_code") or "").strip()
    if not operation_code:
        return {"valid": False, "errors": [{"field": "operationCode", "message": "operationCode is required"}]}
    version = (body.get("version") or "").strip() or None
    payload = body.get("payload")
    if not isinstance(payload, dict):
        return {"valid": False, "errors": [{"field": "payload", "message": "payload must be a JSON object"}]}
    try:
        _validate(operation_code, payload, version)
        resolved = resolve_version(operation_code.upper(), version) or (version or "1.0")
        return {"valid": True, "errors": [], "normalizedVersion": resolved}
    except Exception as e:
        import jsonschema

        if isinstance(e, jsonschema.ValidationError):
            path_str = ".".join(str(p) for p in e.path) if e.path else "payload"
            return {"valid": False, "errors": [{"field": path_str, "message": str(e.message)}]}
        raise


def run_sandbox_mock(body: dict[str, Any]) -> dict[str, Any]:
    """Run mock sandbox test. Returns sandbox result dict."""
    from schema.sandbox_runner import run_mock_sandbox_test

    operation_code = (body.get("operationCode") or body.get("operation_code") or "").strip()
    if not operation_code:
        raise ValueError("operationCode is required")
    payload = body.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    version = (body.get("version") or "").strip() or None
    context = body.get("context")
    if context is not None and not isinstance(context, dict):
        context = {}
    return run_mock_sandbox_test(operation_code, payload, version=version, context=context or {})


def analyze_canonical_request(body: dict[str, Any]) -> dict[str, Any]:
    """Analyze canonical request payload. Returns debug report."""
    from ai.integration_debugger import analyze_canonical_request as _analyze

    operation_code = (body.get("operationCode") or body.get("operation_code") or "").strip()
    if not operation_code:
        raise ValueError("operationCode is required")
    payload = body.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    version = (body.get("version") or "").strip() or None
    enhance_with_ai = body.get("enhanceWithAi") is True
    return _analyze(operation_code, payload, version, enhance_with_ai=enhance_with_ai)


def analyze_flow_draft(body: dict[str, Any]) -> dict[str, Any]:
    """Analyze flow draft. Returns debug report."""
    from ai.integration_debugger import analyze_flow_draft as _analyze

    draft = body.get("draft")
    if draft is None and "operationCode" in body:
        draft = body
    if not isinstance(draft, dict):
        raise ValueError("draft must be a JSON object")
    enhance_with_ai = body.get("enhanceWithAi") is True
    return _analyze(draft, enhance_with_ai=enhance_with_ai)


def analyze_sandbox_result(body: dict[str, Any]) -> dict[str, Any]:
    """Analyze sandbox result. Returns debug report."""
    from ai.integration_debugger import analyze_sandbox_result as _analyze

    result = body.get("result")
    if result is None and "operationCode" in body:
        result = body
    if not isinstance(result, dict):
        raise ValueError("result must be a JSON object")
    enhance_with_ai = body.get("enhanceWithAi") is True
    return _analyze(result, enhance_with_ai=enhance_with_ai)


def run_canonical_preflight(
    payload: dict[str, Any],
    *,
    allowlist_ok: bool | None = None,
    mapping_ok: bool | None = None,
) -> dict[str, Any]:
    """Run canonical preflight. Payload must include sourceVendor, targetVendor, envelope."""
    from schema.canonical_runtime_preflight import run_canonical_preflight as _run

    return _run(payload, allowlist_ok=allowlist_ok, mapping_ok=mapping_ok)


def run_canonical_bridge(
    payload: dict[str, Any],
    *,
    executor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    allowlist_ok: bool | None = None,
    mapping_ok: bool | None = None,
) -> dict[str, Any]:
    """Run canonical bridge. Payload must include sourceVendor, targetVendor, mode, envelope."""
    from schema.canonical_runtime_bridge import run_canonical_bridge as _run

    return _run(payload, executor=executor, allowlist_ok=allowlist_ok, mapping_ok=mapping_ok)
