"""Canonical runtime preflight - validate and resolve runtime prerequisites without execution.

No DB reads in core logic. No external vendor calls. No mutations.
Returns deterministic checks and execution plan.
"""

from __future__ import annotations

from typing import Any

import jsonschema

from schema.canonical_registry import resolve_version
from schema.canonical_validator import validate_request_envelope

PREFLIGHT_NOTE = "Preflight only. No vendor endpoint was called."


def validate_preflight_request(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate preflight request shape. Returns list of errors (empty if valid)."""
    errors: list[dict[str, Any]] = []

    if not isinstance(payload, dict):
        return [{"field": "body", "message": "Request body must be a JSON object."}]

    source = (payload.get("sourceVendor") or payload.get("source_vendor") or "").strip()
    target = (payload.get("targetVendor") or payload.get("target_vendor") or "").strip()
    envelope = payload.get("envelope")

    if not source:
        errors.append({"field": "sourceVendor", "message": "sourceVendor is required and must be non-empty."})
    if not target:
        errors.append({"field": "targetVendor", "message": "targetVendor is required and must be non-empty."})
    if envelope is None:
        errors.append({"field": "envelope", "message": "envelope is required."})
    elif not isinstance(envelope, dict):
        errors.append({"field": "envelope", "message": "envelope must be a JSON object."})

    return errors


def run_canonical_preflight(
    payload: dict[str, Any],
    *,
    allowlist_ok: bool | None = None,
    mapping_ok: bool | None = None,
) -> dict[str, Any]:
    """Run canonical preflight checks. Returns deterministic result.

    Args:
        payload: Preflight request with sourceVendor, targetVendor, envelope.
        allowlist_ok: Optional. If provided, used for VENDOR_PAIR_ALLOWED check.
        mapping_ok: Optional. If provided, used for RUNTIME_MAPPING_FOUND check.

    Returns:
        Preflight result with valid, status, checks, executionPlan, notes.
    """
    errors = validate_preflight_request(payload)
    if errors:
        return _failure_result(
            status="BLOCKED",
            errors=errors,
            checks=_checks_for_validation_failure(errors),
        )

    source = (payload.get("sourceVendor") or payload.get("source_vendor") or "").strip()
    target = (payload.get("targetVendor") or payload.get("target_vendor") or "").strip()
    envelope = payload.get("envelope") or {}

    op_code = (envelope.get("operationCode") or envelope.get("operation_code") or "").strip().upper()
    version_in = (envelope.get("version") or "").strip()
    direction = (envelope.get("direction") or "").strip().upper()

    checks: list[dict[str, Any]] = []
    status = "READY"
    normalized_envelope: dict[str, Any] | None = None

    # 1. Canonical operation resolved
    resolved = resolve_version(op_code, version_in or None)
    if resolved is None:
        checks.append({
            "code": "CANONICAL_OPERATION_RESOLVED",
            "status": "FAIL",
            "message": f"Operation '{op_code}' with version '{version_in or '?'}' not found in canonical registry.",
        })
        return _failure_result(
            status="BLOCKED",
            errors=[{"field": "envelope.operationCode", "message": f"Unknown operation or version: {op_code} {version_in}"}],
            checks=checks,
            operation_code=op_code,
            canonical_version="",
            source_vendor=source,
            target_vendor=target,
        )
    checks.append({
        "code": "CANONICAL_OPERATION_RESOLVED",
        "status": "PASS",
        "message": f"Canonical operation {op_code} {resolved} resolved.",
    })

    # 2. Direction must be REQUEST
    if direction != "REQUEST":
        checks.append({
            "code": "ENVELOPE_DIRECTION_VALID",
            "status": "FAIL",
            "message": f"Envelope direction must be REQUEST, got '{direction}'.",
        })
        return _failure_result(
            status="BLOCKED",
            errors=[{"field": "envelope.direction", "message": "direction must be REQUEST"}],
            checks=checks,
            operation_code=op_code,
            canonical_version=resolved,
            source_vendor=source,
            target_vendor=target,
        )
    checks.append({
        "code": "ENVELOPE_DIRECTION_VALID",
        "status": "PASS",
        "message": "Envelope direction is REQUEST.",
    })

    # 3. Canonical request envelope valid
    try:
        validate_request_envelope(op_code, envelope, resolved)
        checks.append({
            "code": "CANONICAL_REQUEST_VALID",
            "status": "PASS",
            "message": "Canonical request envelope is valid.",
        })
        normalized_envelope = dict(envelope)
        normalized_envelope["version"] = resolved
    except jsonschema.ValidationError as e:
        path_str = ".".join(str(p) for p in e.path) if e.path else "envelope.payload"
        checks.append({
            "code": "CANONICAL_REQUEST_VALID",
            "status": "FAIL",
            "message": str(e.message),
        })
        return _failure_result(
            status="BLOCKED",
            errors=[{"field": path_str, "message": str(e.message)}],
            checks=checks,
            operation_code=op_code,
            canonical_version=resolved,
            source_vendor=source,
            target_vendor=target,
        )

    # 4. Vendor pair / allowlist (optional, from caller)
    if allowlist_ok is not None:
        if allowlist_ok:
            checks.append({
                "code": "VENDOR_PAIR_ALLOWED",
                "status": "PASS",
                "message": f"Vendor pair ({source} -> {target}) is allowed for {op_code}.",
            })
        else:
            checks.append({
                "code": "VENDOR_PAIR_ALLOWED",
                "status": "FAIL",
                "message": f"Vendor pair ({source} -> {target}) is not in allowlist for {op_code}.",
            })
            status = "BLOCKED"
    else:
        checks.append({
            "code": "VENDOR_PAIR_ALLOWED",
            "status": "WARN",
            "message": "Allowlist not verified (preflight runs without DB). Use readiness API for full check.",
        })
        if status == "READY":
            status = "WARN"

    # 5. Runtime mapping (optional, from caller)
    if mapping_ok is not None:
        if mapping_ok:
            checks.append({
                "code": "RUNTIME_MAPPING_FOUND",
                "status": "PASS",
                "message": "Runtime mapping/config found for operation.",
            })
        else:
            checks.append({
                "code": "RUNTIME_MAPPING_FOUND",
                "status": "WARN",
                "message": "Runtime mapping/config not found. Configure mapping for execution.",
            })
            if status == "READY":
                status = "WARN"
    else:
        checks.append({
            "code": "RUNTIME_MAPPING_FOUND",
            "status": "WARN",
            "message": "Mapping not verified (preflight runs without DB). Use readiness API for full check.",
        })
        if status == "READY":
            status = "WARN"

    can_execute = status != "BLOCKED"
    return {
        "valid": can_execute,
        "status": status,
        "operationCode": op_code,
        "canonicalVersion": resolved,
        "sourceVendor": source,
        "targetVendor": target,
        "normalizedEnvelope": normalized_envelope,
        "checks": checks,
        "executionPlan": {
            "mode": "PREFLIGHT_ONLY",
            "canExecute": can_execute,
            "nextStep": "Use existing runtime execute path after preflight passes." if can_execute else "Fix blocked checks before execution.",
        },
        "notes": [PREFLIGHT_NOTE],
    }


def _checks_for_validation_failure(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build minimal checks for validation failure."""
    checks = []
    if any("sourceVendor" in (e.get("field") or "") for e in errors):
        checks.append({
            "code": "SOURCE_VENDOR_VALID",
            "status": "FAIL",
            "message": "sourceVendor is required.",
        })
    if any("targetVendor" in (e.get("field") or "") for e in errors):
        checks.append({
            "code": "TARGET_VENDOR_VALID",
            "status": "FAIL",
            "message": "targetVendor is required.",
        })
    if any("envelope" in (e.get("field") or "") for e in errors):
        checks.append({
            "code": "CANONICAL_REQUEST_VALID",
            "status": "FAIL",
            "message": "Canonical request envelope is invalid.",
        })
    if not checks:
        checks.append({
            "code": "REQUEST_VALID",
            "status": "FAIL",
            "message": "Request validation failed.",
        })
    return checks


def _failure_result(
    *,
    status: str,
    errors: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    operation_code: str = "",
    canonical_version: str = "",
    source_vendor: str = "",
    target_vendor: str = "",
) -> dict[str, Any]:
    """Build failure result."""
    return {
        "valid": False,
        "status": status,
        "operationCode": operation_code,
        "canonicalVersion": canonical_version,
        "sourceVendor": source_vendor,
        "targetVendor": target_vendor,
        "errors": errors,
        "checks": checks,
        "notes": [PREFLIGHT_NOTE],
    }
