"""Canonical mapping engine - deterministic field/path-based transforms.

Preview and validation only. No external calls. No runtime replacement.
"""

from __future__ import annotations

from typing import Any

from schema.canonical_registry import get_operation, resolve_version

PREVIEW_NOTE = "Preview only. No runtime execution performed."

# Registry: (operation_code, version, source_vendor, target_vendor) -> { canonical_to_vendor, vendor_to_canonical }
_MAPPING_REGISTRY: dict[tuple[str, str, str, str], dict[str, Any]] = {}


def _ensure_loaded() -> None:
    """Lazy-load mapping definitions."""
    if _MAPPING_REGISTRY:
        return
    from schema.canonical_mappings.eligibility_v1_lh001_lh002 import (
        ELIGIBILITY_CANONICAL_TO_VENDOR,
        ELIGIBILITY_VENDOR_TO_CANONICAL,
    )
    from schema.canonical_mappings.member_accumulators_v1_lh001_lh002 import (
        ACCUMULATORS_CANONICAL_TO_VENDOR,
        ACCUMULATORS_VENDOR_TO_CANONICAL,
    )

    _MAPPING_REGISTRY[("GET_VERIFY_MEMBER_ELIGIBILITY", "1.0", "LH001", "LH002")] = {
        "canonical_to_vendor": ELIGIBILITY_CANONICAL_TO_VENDOR,
        "vendor_to_canonical": ELIGIBILITY_VENDOR_TO_CANONICAL,
    }
    _MAPPING_REGISTRY[("GET_MEMBER_ACCUMULATORS", "1.0", "LH001", "LH002")] = {
        "canonical_to_vendor": ACCUMULATORS_CANONICAL_TO_VENDOR,
        "vendor_to_canonical": ACCUMULATORS_VENDOR_TO_CANONICAL,
    }


def _extract_with_found(obj: dict[str, Any], path: str) -> tuple[Any, bool]:
    """Extract value using $.path. Returns (value, found)."""
    if not path or not isinstance(path, str) or not str(path).strip().startswith("$."):
        return None, False
    keys = str(path).strip()[2:].split(".")
    if not keys or not all(k.strip() for k in keys):
        return None, False
    keys = [k.strip() for k in keys]
    current: Any = obj
    for key in keys:
        if not isinstance(current, dict):
            return None, False
        if key not in current:
            return None, False
        current = current[key]
    return current, True


def _set_nested(output: dict[str, Any], key_path: str, value: Any) -> None:
    """Set value at dot-separated path."""
    parts = key_path.split(".")
    if not parts:
        return
    target = output
    for part in parts[:-1]:
        if part not in target:
            target[part] = {}
        nest = target[part]
        if not isinstance(nest, dict):
            nest = {}
            target[part] = nest
        target = nest
    target[parts[-1]] = value


def _apply_mapping(input_payload: dict[str, Any], mapping: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Apply mapping rules. Returns (output_payload, violations)."""
    output: dict[str, Any] = {}
    violations: list[str] = []
    for out_key, selector_or_const in mapping.items():
        if isinstance(selector_or_const, str) and str(selector_or_const).strip().startswith("$."):
            value, found = _extract_with_found(input_payload, selector_or_const)
            if not found:
                violations.append(f"missing path {selector_or_const} for field {out_key}")
                continue
            _set_nested(output, out_key, value)
        else:
            _set_nested(output, out_key, selector_or_const)
    return output, violations


def list_mapping_operations() -> list[dict[str, Any]]:
    """List operations that have mapping definitions available."""
    _ensure_loaded()
    seen: set[tuple[str, str]] = set()
    items: list[dict[str, Any]] = []
    for (op_code, version, _src, _tgt) in _MAPPING_REGISTRY:
        key = (op_code, version)
        if key in seen:
            continue
        seen.add(key)
        op = get_operation(op_code, version)
        item: dict[str, Any] = {
            "operationCode": op_code,
            "version": version,
            "title": op.get("title", "") if op else "",
            "description": op.get("description", "") if op else "",
        }
        vendor_pairs = [
            {"sourceVendor": s, "targetVendor": t}
            for (o, v, s, t) in _MAPPING_REGISTRY
            if (o, v) == (op_code, version)
        ]
        item["vendorPairs"] = vendor_pairs
        items.append(item)
    return sorted(items, key=lambda x: (x["operationCode"], x["version"]))


def get_mapping_definition(
    operation_code: str,
    version: str | None = None,
    source_vendor: str | None = None,
    target_vendor: str | None = None,
) -> dict[str, Any] | None:
    """Get mapping definition for operation/vendor-pair. Returns None if not found."""
    _ensure_loaded()
    resolved = resolve_version(operation_code, version)
    if resolved is None:
        return None
    op_code = (operation_code or "").strip().upper()
    src = (source_vendor or "").strip().upper()
    tgt = (target_vendor or "").strip().upper()
    key = (op_code, resolved, src, tgt)
    if key not in _MAPPING_REGISTRY:
        return None
    raw = _MAPPING_REGISTRY[key]
    return {
        "operationCode": op_code,
        "version": resolved,
        "sourceVendor": src,
        "targetVendor": tgt,
        "canonicalToVendor": raw.get("canonical_to_vendor", {}),
        "vendorToCanonical": raw.get("vendor_to_canonical", {}),
    }


def validate_mapping_definition(definition: dict[str, Any]) -> dict[str, Any]:
    """Validate mapping definition structure. Returns { valid, errors, warnings }."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(definition, dict):
        return {"valid": False, "errors": ["Definition must be a JSON object"], "warnings": []}
    if "canonicalToVendor" not in definition and "vendorToCanonical" not in definition:
        errors.append("At least one of canonicalToVendor or vendorToCanonical is required")
    for key in ("canonicalToVendor", "vendorToCanonical"):
        if key in definition:
            val = definition[key]
            if not isinstance(val, dict):
                errors.append(f"{key} must be a JSON object")
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def transform_canonical_to_vendor(
    operation_code: str,
    canonical_payload: dict[str, Any],
    source_vendor: str,
    target_vendor: str,
    version: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Transform canonical payload to vendor payload. Returns (output, violations)."""
    defn = get_mapping_definition(operation_code, version, source_vendor, target_vendor)
    if defn is None:
        return {}, [f"No mapping definition for {operation_code} {version or '?'} {source_vendor}->{target_vendor}"]
    mapping = defn.get("canonicalToVendor") or {}
    return _apply_mapping(canonical_payload, mapping)


def transform_vendor_to_canonical(
    operation_code: str,
    vendor_payload: dict[str, Any],
    source_vendor: str,
    target_vendor: str,
    version: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Transform vendor payload to canonical payload. Returns (output, violations)."""
    defn = get_mapping_definition(operation_code, version, source_vendor, target_vendor)
    if defn is None:
        return {}, [f"No mapping definition for {operation_code} {version or '?'} {source_vendor}->{target_vendor}"]
    mapping = defn.get("vendorToCanonical") or {}
    return _apply_mapping(vendor_payload, mapping)


def preview_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    """Preview a transform. No execution. Returns deterministic preview result."""
    if not isinstance(payload, dict):
        return {
            "valid": False,
            "operationCode": "",
            "version": "",
            "sourceVendor": "",
            "targetVendor": "",
            "direction": "",
            "mappingDefinitionSummary": {"fieldMappings": 0, "constants": 0, "warnings": ["Invalid request body"]},
            "inputPayload": {},
            "outputPayload": {},
            "errors": ["Request body must be a JSON object"],
            "notes": [PREVIEW_NOTE],
        }

    op_code = (payload.get("operationCode") or payload.get("operation_code") or "").strip().upper()
    version_in = (payload.get("version") or "").strip()
    source = (payload.get("sourceVendor") or payload.get("source_vendor") or "").strip()
    target = (payload.get("targetVendor") or payload.get("target_vendor") or "").strip()
    direction = (payload.get("direction") or "").strip().upper()
    input_payload = payload.get("inputPayload") or payload.get("input_payload") or {}

    if not op_code:
        return _preview_error("operationCode is required", payload)
    if not source:
        return _preview_error("sourceVendor is required", payload)
    if not target:
        return _preview_error("targetVendor is required", payload)
    if direction not in ("CANONICAL_TO_VENDOR", "VENDOR_TO_CANONICAL"):
        return _preview_error("direction must be CANONICAL_TO_VENDOR or VENDOR_TO_CANONICAL", payload)
    if not isinstance(input_payload, dict):
        return _preview_error("inputPayload must be a JSON object", payload)

    resolved = resolve_version(op_code, version_in or None)
    if resolved is None:
        return _preview_error(f"Operation {op_code} with version {version_in or '?'} not found", payload)

    defn = get_mapping_definition(op_code, resolved, source, target)
    if defn is None:
        return {
            "valid": False,
            "operationCode": op_code,
            "version": resolved,
            "sourceVendor": source,
            "targetVendor": target,
            "direction": direction,
            "mappingDefinitionSummary": {"fieldMappings": 0, "constants": 0, "warnings": [f"No mapping for {source}->{target}"]},
            "inputPayload": input_payload,
            "outputPayload": {},
            "errors": [f"No mapping definition for {op_code} {resolved} {source}->{target}"],
            "notes": [PREVIEW_NOTE],
        }

    mapping = defn.get("canonicalToVendor") if direction == "CANONICAL_TO_VENDOR" else defn.get("vendorToCanonical")
    mapping = mapping or {}
    field_mappings = sum(1 for v in mapping.values() if isinstance(v, str) and str(v).strip().startswith("$."))
    constants = len(mapping) - field_mappings

    if direction == "CANONICAL_TO_VENDOR":
        output, violations = transform_canonical_to_vendor(op_code, input_payload, source, target, resolved)
    else:
        output, violations = transform_vendor_to_canonical(op_code, input_payload, source, target, resolved)

    valid = len(violations) == 0
    return {
        "valid": valid,
        "operationCode": op_code,
        "version": resolved,
        "sourceVendor": source,
        "targetVendor": target,
        "direction": direction,
        "mappingDefinitionSummary": {
            "fieldMappings": field_mappings,
            "constants": max(0, constants),
            "warnings": violations if not valid else [],
        },
        "inputPayload": input_payload,
        "outputPayload": output,
        "errors": violations if not valid else [],
        "notes": [PREVIEW_NOTE],
    }


def _preview_error(message: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Build error preview result."""
    return {
        "valid": False,
        "operationCode": (payload.get("operationCode") or "").strip().upper(),
        "version": (payload.get("version") or "").strip(),
        "sourceVendor": (payload.get("sourceVendor") or "").strip(),
        "targetVendor": (payload.get("targetVendor") or "").strip(),
        "direction": (payload.get("direction") or "").strip().upper(),
        "mappingDefinitionSummary": {"fieldMappings": 0, "constants": 0, "warnings": [message]},
        "inputPayload": payload.get("inputPayload") or payload.get("input_payload") or {},
        "outputPayload": {},
        "errors": [message],
        "notes": [PREVIEW_NOTE],
    }


def validate_mapping_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate mapping availability and payload transformability. Returns validation result."""
    result = preview_mapping(payload)
    if result.get("valid"):
        return {
            "valid": True,
            "operationCode": result["operationCode"],
            "version": result["version"],
            "sourceVendor": result["sourceVendor"],
            "targetVendor": result["targetVendor"],
            "direction": result["direction"],
            "mappingAvailable": True,
            "warnings": [],
            "notes": [PREVIEW_NOTE],
        }
    return {
        "valid": False,
        "operationCode": result.get("operationCode", ""),
        "version": result.get("version", ""),
        "sourceVendor": result.get("sourceVendor", ""),
        "targetVendor": result.get("targetVendor", ""),
        "direction": result.get("direction", ""),
        "mappingAvailable": not any("No mapping definition" in str(e) for e in result.get("errors", [])),
        "warnings": result.get("errors", []),
        "notes": [PREVIEW_NOTE],
    }
