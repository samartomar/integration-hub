"""Flow runtime handoff - generate canonical execution package from validated flow draft.

Read-only. No execution. Optionally runs canonical preflight.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from schema.canonical_envelope import build_envelope
from schema.canonical_registry import get_operation, resolve_version
from schema.canonical_runtime_preflight import run_canonical_preflight
from schema.flow_draft_schema import FlowDraftValidationError, normalize_flow_draft, validate_flow_draft

HANDOFF_NOTES = [
    "Flow handoff package generated from validated draft.",
    "No runtime execution performed.",
]


def build_flow_runtime_handoff(payload: dict[str, Any]) -> dict[str, Any]:
    """Build canonical execution package from flow draft.

    Args:
        payload: Handoff request with draft, optional payload, optional context, runPreflight.

    Returns:
        Handoff result with valid, flowName, operationCode, canonicalVersion, sourceVendor,
        targetVendor, triggerType, mappingMode, canonicalExecutionPackage, optional preflight, notes.
    """
    if not isinstance(payload, dict):
        return _invalid_result("Request body must be a JSON object.")

    draft = payload.get("draft")
    if not isinstance(draft, dict):
        return _invalid_result("draft is required and must be a JSON object.")

    try:
        validate_flow_draft(draft)
        normalized = normalize_flow_draft(draft)
    except FlowDraftValidationError as e:
        return _invalid_result(
            e.message or str(e),
            field=e.field,
        )

    op_code = normalized.get("operationCode", "").strip().upper()
    canonical_version = normalized.get("version", "").strip()
    source = normalized.get("sourceVendor", "").strip()
    target = normalized.get("targetVendor", "").strip()
    flow_name = normalized.get("name", "").strip()
    trigger = normalized.get("trigger") or {}
    trigger_type = (trigger.get("type") or "MANUAL").strip().upper()
    mapping_mode = (normalized.get("mappingMode") or "CANONICAL_FIRST").strip().upper()

    # Resolve payload: explicit payload, or canonical example request
    explicit_payload = payload.get("payload")
    if isinstance(explicit_payload, dict) and len(explicit_payload) > 0:
        req_payload = dict(explicit_payload)
    else:
        op_detail = get_operation(op_code, canonical_version)
        if op_detail and op_detail.get("examples", {}).get("request"):
            req_payload = dict(op_detail["examples"]["request"])
        else:
            req_payload = {}

    context = payload.get("context")
    if not isinstance(context, dict):
        context = {}

    correlation_id = f"corr-flow-{uuid.uuid4().hex[:12]}"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    envelope = build_envelope(
        operation_code=op_code,
        version=canonical_version,
        direction="REQUEST",
        payload=req_payload,
        correlation_id=correlation_id,
        timestamp=timestamp,
        context=context,
    )

    canonical_execution_package: dict[str, Any] = {
        "sourceVendor": source,
        "targetVendor": target,
        "envelope": envelope,
    }

    result: dict[str, Any] = {
        "valid": True,
        "flowName": flow_name,
        "operationCode": op_code,
        "canonicalVersion": canonical_version,
        "sourceVendor": source,
        "targetVendor": target,
        "triggerType": trigger_type,
        "mappingMode": mapping_mode,
        "canonicalExecutionPackage": canonical_execution_package,
        "notes": list(HANDOFF_NOTES),
    }

    run_preflight = payload.get("runPreflight") is True
    if run_preflight:
        preflight_payload = {
            "sourceVendor": source,
            "targetVendor": target,
            "envelope": envelope,
        }
        preflight = run_canonical_preflight(preflight_payload)
        result["preflight"] = preflight

    return result


def maybe_run_flow_handoff_preflight(handoff: dict[str, Any]) -> dict[str, Any]:
    """Run canonical preflight for an existing handoff package.

    Args:
        handoff: Result from build_flow_runtime_handoff (must have canonicalExecutionPackage).

    Returns:
        Handoff with preflight result attached. Does not mutate input.
    """
    pkg = handoff.get("canonicalExecutionPackage")
    if not isinstance(pkg, dict):
        return dict(handoff)

    envelope = pkg.get("envelope")
    source = pkg.get("sourceVendor") or handoff.get("sourceVendor", "")
    target = pkg.get("targetVendor") or handoff.get("targetVendor", "")

    if not isinstance(envelope, dict) or not source or not target:
        return dict(handoff)

    preflight_payload = {"sourceVendor": source, "targetVendor": target, "envelope": envelope}
    preflight = run_canonical_preflight(preflight_payload)

    out = dict(handoff)
    out["preflight"] = preflight
    return out


def _invalid_result(message: str, field: str | None = None) -> dict[str, Any]:
    """Build invalid handoff result."""
    errors: list[dict[str, Any]] = [{"message": message}]
    if field:
        errors[0]["field"] = field
    return {
        "valid": False,
        "flowName": "",
        "operationCode": "",
        "canonicalVersion": "",
        "sourceVendor": "",
        "targetVendor": "",
        "triggerType": "MANUAL",
        "mappingMode": "CANONICAL_FIRST",
        "canonicalExecutionPackage": None,
        "errors": errors,
        "notes": list(HANDOFF_NOTES),
    }
