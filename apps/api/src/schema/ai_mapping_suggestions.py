"""AI mapping suggestions - advisory only. Deterministic mappings remain authoritative.

No persistence. No runtime execution. No automatic apply.
"""

from __future__ import annotations

from typing import Any

from schema.canonical_mapping_engine import get_mapping_definition
from schema.canonical_registry import get_operation, resolve_version

SUGGESTION_NOTES = [
    "AI mapping suggestions are advisory only.",
    "Deterministic mapping definitions remain authoritative.",
]


def build_mapping_suggestion_request(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Build redacted mapping context for AI Gateway. Returns None if invalid."""
    if not isinstance(payload, dict):
        return None
    op_code = (payload.get("operationCode") or payload.get("operation_code") or "").strip().upper()
    if not op_code:
        return None
    source = (payload.get("sourceVendor") or payload.get("source_vendor") or "").strip()
    target = (payload.get("targetVendor") or payload.get("target_vendor") or "").strip()
    if not source or not target:
        return None
    version_in = (payload.get("version") or "").strip()
    direction = (payload.get("direction") or "CANONICAL_TO_VENDOR").strip().upper()
    if direction not in ("CANONICAL_TO_VENDOR", "VENDOR_TO_CANONICAL"):
        return None

    resolved = resolve_version(op_code, version_in or None)
    if resolved is None:
        return None

    defn = get_mapping_definition(op_code, resolved, source, target)
    op_detail = get_operation(op_code, resolved)

    # Build safe schema summaries (field names only, no values)
    canonical_schema: dict[str, Any] = {}
    if op_detail:
        if direction == "CANONICAL_TO_VENDOR":
            req_schema = op_detail.get("requestPayloadSchema") or {}
            if isinstance(req_schema, dict) and req_schema.get("properties"):
                canonical_schema = {"properties": list(req_schema["properties"].keys())}
        else:
            resp_schema = op_detail.get("responsePayloadSchema") or {}
            if isinstance(resp_schema, dict) and resp_schema.get("properties"):
                canonical_schema = {"properties": list(resp_schema["properties"].keys())}

    vendor_shape = payload.get("vendorShape") or payload.get("vendor_shape")
    if isinstance(vendor_shape, dict):
        vendor_shape = {"properties": list(vendor_shape.keys()) if vendor_shape else []}
    else:
        vendor_shape = {}

    existing: dict[str, Any] = {}
    if defn:
        mapping = defn.get("canonicalToVendor") if direction == "CANONICAL_TO_VENDOR" else defn.get("vendorToCanonical")
        if isinstance(mapping, dict):
            existing = dict(mapping)

    # Sanitize input payload example - use structure only, redact values
    input_example = payload.get("inputPayloadExample") or payload.get("input_payload_example")
    if isinstance(input_example, dict):
        input_example = {k: "[REDACTED]" for k in input_example}

    return {
        "operationCode": op_code,
        "version": resolved,
        "sourceVendor": source,
        "targetVendor": target,
        "direction": direction,
        "canonicalSchema": canonical_schema,
        "vendorShape": vendor_shape,
        "existingMappingDefinition": existing,
        "inputPayloadExample": input_example,
    }


def _deterministic_baseline(defn: dict[str, Any] | None, direction: str) -> dict[str, Any]:
    """Build deterministic baseline summary from existing mapping."""
    if defn is None:
        return {"fieldMappings": 0, "constants": 0, "warnings": ["No deterministic mapping exists yet."]}
    mapping = defn.get("canonicalToVendor") if direction == "CANONICAL_TO_VENDOR" else defn.get("vendorToCanonical")
    mapping = mapping or {}
    field_mappings = sum(1 for v in mapping.values() if isinstance(v, str) and str(v).strip().startswith("$."))
    constants = max(0, len(mapping) - field_mappings)
    return {
        "fieldMappings": field_mappings,
        "constants": constants,
        "warnings": [],
    }


def compare_mapping_definition_to_suggestion(
    definition: dict[str, Any],
    suggestion: dict[str, Any],
) -> dict[str, Any]:
    """Compare deterministic mapping to AI suggestion. Returns unchanged, added, changed."""
    def_mapping = definition if isinstance(definition, dict) else {}
    sugg_mapping = suggestion.get("proposedFieldMappings") or []
    if not isinstance(sugg_mapping, list):
        sugg_mapping = []

    # Build suggestion dict: to -> from
    sugg_dict: dict[str, str] = {}
    for item in sugg_mapping:
        if isinstance(item, dict):
            to_key = item.get("to") or item.get("from")
            from_key = item.get("from") or item.get("to")
            if to_key and from_key:
                sugg_dict[str(to_key)] = str(from_key)

    # Def format: out_key -> $.selector
    unchanged: list[dict[str, str]] = []
    added: list[dict[str, str]] = []
    changed: list[dict[str, str]] = []

    for out_key, selector_or_const in def_mapping.items():
        if not isinstance(selector_or_const, str) or not str(selector_or_const).strip().startswith("$."):
            continue
        from_path = str(selector_or_const).strip()[2:]  # strip $.
        from_field = from_path.split(".")[0] if "." in from_path else from_path
        sugg_from = sugg_dict.get(out_key)
        if sugg_from is None:
            changed.append({"field": out_key, "from": from_field, "to": out_key, "note": "removed in suggestion"})
        elif sugg_from == from_field or sugg_from == from_path:
            unchanged.append({"from": from_field, "to": out_key})
        else:
            changed.append({"from": from_field, "to": out_key, "suggestedFrom": sugg_from})

    for out_key, from_val in sugg_dict.items():
        if out_key not in def_mapping:
            added.append({"from": from_val, "to": out_key})

    return {
        "unchanged": unchanged,
        "added": added,
        "changed": changed,
    }


def suggest_mapping_improvements(
    payload: dict[str, Any],
    *,
    ai_invoker: Any = None,
) -> dict[str, Any]:
    """
    Build deterministic baseline + optional AI suggestion.

    ai_invoker: callable(context) -> ai_suggestion_dict | None. If None, skips AI.
    """
    op_code = (payload.get("operationCode") or payload.get("operation_code") or "").strip().upper()
    source = (payload.get("sourceVendor") or payload.get("source_vendor") or "").strip()
    target = (payload.get("targetVendor") or payload.get("target_vendor") or "").strip()
    version_in = (payload.get("version") or "").strip()
    direction = (payload.get("direction") or "CANONICAL_TO_VENDOR").strip().upper()

    if not op_code or not source or not target:
        return {
            "valid": False,
            "operationCode": op_code or "",
            "version": "",
            "sourceVendor": source,
            "targetVendor": target,
            "direction": direction,
            "deterministicBaseline": {"fieldMappings": 0, "constants": 0, "warnings": ["Missing operationCode, sourceVendor, or targetVendor."]},
            "aiSuggestion": None,
            "comparison": None,
            "notes": SUGGESTION_NOTES,
        }

    resolved = resolve_version(op_code, version_in or None)
    if resolved is None:
        return {
            "valid": False,
            "operationCode": op_code,
            "version": "",
            "sourceVendor": source,
            "targetVendor": target,
            "direction": direction,
            "deterministicBaseline": {"fieldMappings": 0, "constants": 0, "warnings": [f"Operation {op_code} version not found."]},
            "aiSuggestion": None,
            "comparison": None,
            "notes": SUGGESTION_NOTES,
        }

    defn = get_mapping_definition(op_code, resolved, source, target)
    baseline = _deterministic_baseline(defn, direction)

    ai_suggestion: dict[str, Any] | None = None
    comparison: dict[str, Any] | None = None

    if ai_invoker and callable(ai_invoker):
        ctx = build_mapping_suggestion_request(payload)
        if ctx:
            try:
                ai_result = ai_invoker(ctx)
                if isinstance(ai_result, dict) and (ai_result.get("proposedFieldMappings") or ai_result.get("summary")):
                    ai_suggestion = {
                        "summary": ai_result.get("summary", ""),
                        "proposedFieldMappings": ai_result.get("proposedFieldMappings", []),
                        "proposedConstants": ai_result.get("proposedConstants", []),
                        "warnings": list(ai_result.get("warnings", [])) + ["Suggestion is advisory only and has not been applied."],
                        "confidence": ai_result.get("confidence", "medium"),
                    }
                    # Build definition-like dict for comparison
                    def_like: dict[str, Any] = {}
                    if defn:
                        mapping = defn.get("canonicalToVendor") if direction == "CANONICAL_TO_VENDOR" else defn.get("vendorToCanonical")
                        def_like = dict(mapping or {})
                    sugg_like: dict[str, Any] = {}
                    for item in ai_suggestion.get("proposedFieldMappings", []):
                        if isinstance(item, dict):
                            to_k = item.get("to")
                            from_v = item.get("from")
                            if to_k and from_v:
                                sugg_like[str(to_k)] = f"$.{from_v}" if not from_v.startswith("$.") else from_v
                    comparison = compare_mapping_definition_to_suggestion(def_like, {"proposedFieldMappings": ai_suggestion["proposedFieldMappings"]})
            except Exception:
                ai_suggestion = {
                    "summary": "",
                    "proposedFieldMappings": [],
                    "proposedConstants": [],
                    "warnings": ["AI suggestion unavailable."],
                    "confidence": "none",
                }

    out: dict[str, Any] = {
        "valid": True,
        "operationCode": op_code,
        "version": resolved,
        "sourceVendor": source,
        "targetVendor": target,
        "direction": direction,
        "deterministicBaseline": baseline,
        "aiSuggestion": ai_suggestion,
        "comparison": comparison,
        "notes": SUGGESTION_NOTES,
    }
    if defn:
        mapping = defn.get("canonicalToVendor") if direction == "CANONICAL_TO_VENDOR" else defn.get("vendorToCanonical")
        if isinstance(mapping, dict):
            out["existingMappingDefinition"] = dict(mapping)
    return out
