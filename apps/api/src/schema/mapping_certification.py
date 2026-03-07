"""Mapping certification - deterministic fixture-based verification.

No runtime execution. No persistence. No LLM-generated authority.
Uses canonical_mapping_engine for transforms. Certifies existing deterministic mappings.
"""

from __future__ import annotations

import json
from typing import Any

from schema.canonical_mapping_engine import preview_mapping
from schema.canonical_registry import resolve_version
from schema.mapping_fixtures import list_mapping_fixtures

CERTIFICATION_NOTE = "Certification is deterministic and fixture-based."
NO_RUNTIME_NOTE = "No runtime execution performed."


def _deep_equal(a: Any, b: Any) -> bool:
    """Compare two values for equality (handles dicts, lists, primitives)."""
    if type(a) != type(b):
        return False
    if isinstance(a, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_deep_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        if len(a) != len(b):
            return False
        return all(_deep_equal(x, y) for x, y in zip(a, b))
    return a == b


def list_mapping_fixtures_api(
    operation_code: str | None = None,
    version: str | None = None,
    source_vendor: str | None = None,
    target_vendor: str | None = None,
    fixture_set: str = "default",
) -> dict[str, Any]:
    """List available fixtures for certification. fixture_set reserved for future use."""
    fixtures = list_mapping_fixtures(operation_code, version, source_vendor, target_vendor)
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for f in fixtures:
        fid = f.get("fixtureId", "")
        direction = f.get("direction", "")
        key = (fid, direction)
        if key in seen:
            continue
        seen.add(key)
        items.append({
            "fixtureId": fid,
            "direction": direction,
            "notes": f.get("notes", []),
        })
    return {
        "fixtureSet": fixture_set,
        "items": items,
        "notes": [CERTIFICATION_NOTE, NO_RUNTIME_NOTE],
    }


def run_mapping_certification(payload: dict[str, Any]) -> dict[str, Any]:
    """Run deterministic certification against fixture cases.

    Certifies the current deterministic mapping definition. If candidateMapping
    is supplied, returns a not-supported warning (engine does not support dynamic
    mapping injection).
    """
    if not isinstance(payload, dict):
        return {
            "valid": False,
            "operationCode": "",
            "version": "",
            "sourceVendor": "",
            "targetVendor": "",
            "direction": "",
            "fixtureSet": "default",
            "summary": {"passed": 0, "failed": 0, "warnings": 0, "status": "FAIL"},
            "results": [],
            "notes": ["Request body must be a JSON object."],
        }

    op_code = (payload.get("operationCode") or payload.get("operation_code") or "").strip().upper()
    version_in = (payload.get("version") or "").strip()
    source = (payload.get("sourceVendor") or payload.get("source_vendor") or "").strip()
    target = (payload.get("targetVendor") or payload.get("target_vendor") or "").strip()
    direction = (payload.get("direction") or "CANONICAL_TO_VENDOR").strip().upper()
    fixture_set = (payload.get("fixtureSet") or payload.get("fixture_set") or "default").strip()
    candidate_mapping = payload.get("candidateMapping") or payload.get("candidate_mapping")

    if candidate_mapping is not None:
        return {
            "valid": False,
            "operationCode": op_code,
            "version": version_in or "1.0",
            "sourceVendor": source,
            "targetVendor": target,
            "direction": direction,
            "fixtureSet": fixture_set,
            "summary": {"passed": 0, "failed": 0, "warnings": 1, "status": "WARN"},
            "results": [],
            "notes": [
                "candidateMapping is not supported. Certification uses the current deterministic mapping definition only.",
                CERTIFICATION_NOTE,
                NO_RUNTIME_NOTE,
            ],
        }

    if not op_code:
        return _cert_error("operationCode is required", op_code, version_in, source, target, direction, fixture_set)
    if not source:
        return _cert_error("sourceVendor is required", op_code, version_in, source, target, direction, fixture_set)
    if not target:
        return _cert_error("targetVendor is required", op_code, version_in, source, target, direction, fixture_set)
    if direction not in ("CANONICAL_TO_VENDOR", "VENDOR_TO_CANONICAL"):
        return _cert_error(
            "direction must be CANONICAL_TO_VENDOR or VENDOR_TO_CANONICAL",
            op_code, version_in, source, target, direction, fixture_set,
        )

    resolved = resolve_version(op_code, version_in or None)
    if resolved is None:
        return _cert_error(
            f"Operation {op_code} version not found",
            op_code, version_in, source, target, direction, fixture_set,
        )

    fixtures = list_mapping_fixtures(op_code, resolved, source, target)
    if not fixtures:
        return _cert_error(
            f"No fixtures found for {op_code} {resolved} {source}->{target}",
            op_code, resolved, source, target, direction, fixture_set,
        )

    # Filter by direction
    fixtures = [f for f in fixtures if (f.get("direction") or "").strip().upper() == direction]
    if not fixtures:
        return _cert_error(
            f"No fixtures found for direction {direction}",
            op_code, resolved, source, target, direction, fixture_set,
        )

    results: list[dict[str, Any]] = []
    passed = 0
    failed = 0
    warnings = 0

    for f in fixtures:
        fid = f.get("fixtureId", "unknown")
        input_payload = f.get("inputPayload") or {}
        expected = f.get("expectedOutput") or {}

        preview_payload = {
            "operationCode": op_code,
            "version": resolved,
            "sourceVendor": source,
            "targetVendor": target,
            "direction": direction,
            "inputPayload": input_payload,
        }
        preview_result = preview_mapping(preview_payload)
        actual = preview_result.get("outputPayload") or {}
        valid = preview_result.get("valid", False)
        errors = preview_result.get("errors") or []

        if not valid and errors:
            results.append({
                "fixtureId": fid,
                "status": "FAIL",
                "inputPayload": input_payload,
                "expectedOutput": expected,
                "actualOutput": actual,
                "notes": errors,
            })
            failed += 1
            continue

        if _deep_equal(actual, expected):
            results.append({
                "fixtureId": fid,
                "status": "PASS",
                "inputPayload": input_payload,
                "expectedOutput": expected,
                "actualOutput": actual,
                "notes": [],
            })
            passed += 1
        else:
            results.append({
                "fixtureId": fid,
                "status": "FAIL",
                "inputPayload": input_payload,
                "expectedOutput": expected,
                "actualOutput": actual,
                "notes": ["Output does not match expected. Run mapping preview to inspect."],
            })
            failed += 1

    summary = summarize_mapping_certification({"passed": passed, "failed": failed, "warnings": warnings})
    return {
        "valid": failed == 0,
        "operationCode": op_code,
        "version": resolved,
        "sourceVendor": source,
        "targetVendor": target,
        "direction": direction,
        "fixtureSet": fixture_set,
        "summary": summary,
        "results": results,
        "notes": [CERTIFICATION_NOTE, NO_RUNTIME_NOTE],
    }


def summarize_mapping_certification(counts: dict[str, Any]) -> dict[str, Any]:
    """Build certification summary from passed/failed/warnings counts."""
    passed = int(counts.get("passed") or 0)
    failed = int(counts.get("failed") or 0)
    warnings = int(counts.get("warnings") or 0)
    if failed > 0:
        status = "FAIL"
    elif warnings > 0:
        status = "WARN"
    else:
        status = "PASS"
    return {
        "passed": passed,
        "failed": failed,
        "warnings": warnings,
        "status": status,
    }


def _cert_error(
    message: str,
    op_code: str,
    version: str,
    source: str,
    target: str,
    direction: str,
    fixture_set: str,
) -> dict[str, Any]:
    """Build certification error result."""
    return {
        "valid": False,
        "operationCode": op_code,
        "version": version or "1.0",
        "sourceVendor": source,
        "targetVendor": target,
        "direction": direction,
        "fixtureSet": fixture_set,
        "summary": {"passed": 0, "failed": 0, "warnings": 0, "status": "FAIL"},
        "results": [],
        "notes": [message, CERTIFICATION_NOTE, NO_RUNTIME_NOTE],
    }
