"""Deterministic integration debugger - analyze canonical requests, flow drafts, sandbox results.

No DB reads, no real model calls. Uses Canon, Flow, and Sandbox outputs as inputs.
Returns structured findings and remediation guidance.
"""

from __future__ import annotations

from typing import Any

import jsonschema

from schema.canonical_registry import get_operation, resolve_version
from schema.canonical_validator import validate_request
from schema.flow_draft_schema import FlowDraftValidationError, normalize_flow_draft, validate_flow_draft

DEBUG_NOTE = "Deterministic debugger only. No LLM or vendor endpoint was used."


def _path_to_field(path: tuple[str | int, ...]) -> str:
    """Convert jsonschema path to field string like payload.date."""
    if not path:
        return "payload"
    parts = []
    for p in path:
        if isinstance(p, int):
            parts.append(f"[{p}]")
        else:
            parts.append(str(p))
    return "payload." + ".".join(parts).replace(".[", "[")


def _infer_finding_code(msg: str, field: str) -> str:
    """Infer finding code from validation message."""
    m = (msg or "").lower()
    if "required" in m or "missing" in m:
        return "MISSING_REQUIRED_FIELD"
    if "pattern" in m or "match" in m or "yyyy-mm-dd" in m or "date" in m:
        return "INVALID_DATE_FORMAT"
    if "enum" in m or "one of" in m or "not one of" in m:
        return "INVALID_ENUM"
    if "type" in m or "not of type" in m:
        return "TYPE_MISMATCH"
    if "not found" in m:
        return "UNKNOWN_OPERATION"
    return "VALIDATION_ERROR"


def analyze_canonical_request(
    operation_code: str,
    payload: dict[str, Any],
    version: str | None = None,
) -> dict[str, Any]:
    """Analyze canonical request payload. Returns structured debug report."""
    op_code = (operation_code or "").strip().upper()
    version_in = (version or "").strip() or None

    findings: list[dict[str, Any]] = []
    status = "PASS"
    summary = ""
    normalized_payload: dict[str, Any] | None = None

    # Check operation exists
    resolved = resolve_version(op_code, version_in)
    if resolved is None:
        return build_debug_summary(
            debug_type="CANONICAL_REQUEST",
            status="FAIL",
            operation_code=op_code,
            version=version_in or "?",
            summary=f"Operation '{op_code}' with version '{version_in}' not found in canonical registry.",
            findings=[
                {
                    "severity": "ERROR",
                    "code": "UNKNOWN_OPERATION",
                    "title": "Unknown operation",
                    "message": f"operationCode '{op_code}' with version '{version_in}' not found.",
                    "field": "operationCode",
                    "suggestion": "Use a registered operation like GET_VERIFY_MEMBER_ELIGIBILITY with version 1.0 or v1.",
                }
            ],
            normalized_artifacts={},
        )

    # Version alias note if v1 used
    if version_in and version_in.lower() == "v1":
        findings.append({
            "severity": "INFO",
            "code": "VERSION_ALIAS_RESOLVED",
            "title": "Version alias resolved",
            "message": f"Version alias 'v1' resolved to official version '{resolved}'.",
            "field": "version",
            "suggestion": None,
        })

    # Validate payload
    if not isinstance(payload, dict):
        findings.append({
            "severity": "ERROR",
            "code": "INVALID_PAYLOAD",
            "title": "Invalid payload",
            "message": "Payload must be a JSON object.",
            "field": "payload",
            "suggestion": "Provide a valid request payload object.",
        })
        status = "FAIL"
    else:
        try:
            validate_request(op_code, payload, resolved)
            normalized_payload = dict(payload)
            if not findings:
                summary = f"Request payload is valid for {op_code} {resolved}."
            else:
                summary = f"Request payload is valid for {op_code} {resolved}. Version alias was resolved."
        except jsonschema.ValidationError as e:
            status = "FAIL"
            path_str = _path_to_field(e.path) if e.path else "payload"
            code = _infer_finding_code(str(e.message), path_str)
            suggestion = "Use a date like 2025-03-06." if "date" in str(e.message).lower() or "pattern" in str(e.message).lower() else None
            if not suggestion and "enum" in str(e.message).lower():
                suggestion = "Use a value from the allowed enum (e.g. ACTIVE, INACTIVE for status)."
            findings.append({
                "severity": "ERROR",
                "code": code,
                "title": code.replace("_", " ").lower().title(),
                "message": f"Field {path_str}: {e.message}",
                "field": path_str,
                "suggestion": suggestion,
            })
            summary = f"Request payload validation failed for {op_code} {resolved}."

    if status == "PASS" and not summary:
        summary = f"Request payload is valid for {op_code} {resolved}."

    return build_debug_summary(
        debug_type="CANONICAL_REQUEST",
        status=status,
        operation_code=op_code,
        version=resolved,
        summary=summary,
        findings=findings,
        normalized_artifacts={"payload": normalized_payload} if normalized_payload else {},
    )


def analyze_flow_draft(draft: dict[str, Any]) -> dict[str, Any]:
    """Analyze flow draft. Returns structured debug report."""
    findings: list[dict[str, Any]] = []
    status = "PASS"
    summary = ""
    normalized_draft: dict[str, Any] | None = None

    if not isinstance(draft, dict):
        return build_debug_summary(
            debug_type="FLOW_DRAFT",
            status="FAIL",
            operation_code="",
            version="",
            summary="Draft must be a JSON object.",
            findings=[
                {
                    "severity": "ERROR",
                    "code": "INVALID_DRAFT",
                    "title": "Invalid draft",
                    "message": "Draft must be a JSON object.",
                    "field": "draft",
                    "suggestion": "Provide a valid flow draft object.",
                }
            ],
            normalized_artifacts={},
        )

    try:
        validate_flow_draft(draft)
        normalized_draft = normalize_flow_draft(draft)
        op_code = normalized_draft.get("operationCode", "")
        version = normalized_draft.get("version", "")

        # Version alias note
        version_in = (draft.get("version") or "").strip().lower()
        if version_in == "v1" and version == "1.0":
            findings.append({
                "severity": "INFO",
                "code": "VERSION_ALIAS_NORMALIZED",
                "title": "Version alias normalized",
                "message": "Version alias 'v1' normalized to official version '1.0'.",
                "field": "version",
                "suggestion": None,
            })

        summary = f"Flow draft is valid for {op_code} {version}."
    except FlowDraftValidationError as e:
        status = "FAIL"
        field = e.field or "draft"
        code = "UNKNOWN_OPERATION" if "not found" in (e.message or "").lower() else "VALIDATION_ERROR"
        if "trigger" in (field or "").lower():
            code = "INVALID_TRIGGER_TYPE"
        elif "mapping" in (field or "").lower():
            code = "INVALID_MAPPING_MODE"
        elif "source" in (field or "").lower():
            code = "MISSING_SOURCE_VENDOR"
        elif "target" in (field or "").lower():
            code = "MISSING_TARGET_VENDOR"
        elif "name" in (field or "").lower():
            code = "MISSING_NAME"

        findings.append({
            "severity": "ERROR",
            "code": code,
            "title": code.replace("_", " ").lower().title(),
            "message": e.message or str(e),
            "field": field,
            "suggestion": "Use MANUAL or API for trigger.type; use CANONICAL_FIRST for mappingMode." if "trigger" in (field or "").lower() or "mapping" in (field or "").lower() else None,
        })
        op_code = (draft.get("operationCode") or draft.get("operation_code") or "").strip().upper()
        version = (draft.get("version") or "").strip()
        summary = f"Flow draft validation failed: {e.message}"

    return build_debug_summary(
        debug_type="FLOW_DRAFT",
        status=status,
        operation_code=normalized_draft.get("operationCode", "") if normalized_draft else (draft.get("operationCode") or ""),
        version=normalized_draft.get("version", "") if normalized_draft else "",
        summary=summary,
        findings=findings,
        normalized_artifacts={"draft": normalized_draft} if normalized_draft else {},
    )


def analyze_sandbox_result(result: dict[str, Any]) -> dict[str, Any]:
    """Analyze sandbox result. Returns structured debug report."""
    findings: list[dict[str, Any]] = []
    status = "PASS"
    summary = ""

    if not isinstance(result, dict):
        return build_debug_summary(
            debug_type="SANDBOX_RESULT",
            status="FAIL",
            operation_code="",
            version="",
            summary="Result must be a JSON object.",
            findings=[
                {
                    "severity": "ERROR",
                    "code": "INVALID_RESULT",
                    "title": "Invalid result",
                    "message": "Result must be a JSON object.",
                    "field": "result",
                    "suggestion": "Provide a valid sandbox result object.",
                }
            ],
            normalized_artifacts={},
        )

    op_code = (result.get("operationCode") or "").strip()
    version = (result.get("version") or "").strip()
    valid = result.get("valid", False)
    req_env = result.get("requestEnvelope")
    resp_env = result.get("responseEnvelope")
    errors = result.get("errors") or []

    # Mock-only note
    findings.append({
        "severity": "INFO",
        "code": "MOCK_ONLY",
        "title": "Mock-only execution",
        "message": "Sandbox result is from mock execution. No vendor endpoint was called.",
        "field": None,
        "suggestion": None,
    })

    if not valid:
        status = "FAIL"
        for err in errors:
            if isinstance(err, dict):
                findings.append({
                    "severity": "ERROR",
                    "code": err.get("field", "VALIDATION_ERROR").upper().replace(".", "_") or "VALIDATION_ERROR",
                    "title": "Validation error",
                    "message": err.get("message", str(err)),
                    "field": err.get("field"),
                    "suggestion": None,
                })
        summary = f"Sandbox result is invalid for {op_code} {version}. {len(errors)} error(s) found."
    else:
        if not isinstance(req_env, dict) or not req_env:
            findings.append({
                "severity": "WARNING",
                "code": "MISSING_REQUEST_ENVELOPE",
                "title": "Missing request envelope",
                "message": "Request envelope is missing or empty.",
                "field": "requestEnvelope",
                "suggestion": None,
            })
        if not isinstance(resp_env, dict) or not resp_env:
            findings.append({
                "severity": "WARNING",
                "code": "MISSING_RESPONSE_ENVELOPE",
                "title": "Missing response envelope",
                "message": "Response envelope is missing or empty.",
                "field": "responseEnvelope",
                "suggestion": None,
            })
        if status == "PASS":
            summary = f"Sandbox result is valid for {op_code} {version}. Mock execution completed successfully."

    return build_debug_summary(
        debug_type="SANDBOX_RESULT",
        status=status,
        operation_code=op_code,
        version=version,
        summary=summary,
        findings=findings,
        normalized_artifacts={"sandboxResult": result},
    )


def build_debug_summary(
    debug_type: str,
    status: str,
    operation_code: str,
    version: str,
    summary: str,
    findings: list[dict[str, Any]],
    normalized_artifacts: dict[str, Any],
) -> dict[str, Any]:
    """Build structured debug report."""
    return {
        "debugType": debug_type,
        "status": status,
        "operationCode": operation_code,
        "version": version,
        "summary": summary,
        "findings": findings,
        "normalizedArtifacts": normalized_artifacts,
        "notes": [DEBUG_NOTE],
    }
