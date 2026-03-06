"""Canonical operation registry - code-based source of truth for canonical models.

Provides list_operations, get_operation, and resolve_version.
Official version format: "1.0". Backward compatibility: "v1" -> "1.0".
"""

from __future__ import annotations

from typing import Any

# Registry: operation_code -> { official_version -> model }
_REGISTRY: dict[str, dict[str, Any]] = {}
# Alias map: operation_code -> { alias -> official_version }
_ALIASES: dict[str, dict[str, str]] = {}


def _ensure_loaded() -> None:
    """Lazy-load and register canonical models on first use."""
    if _REGISTRY:
        return
    from schema.canonical_models import eligibility_v1
    from schema.canonical_models import member_accumulators_v1

    _register_operation(eligibility_v1)
    _register_operation(member_accumulators_v1)


def _register_operation(model: Any) -> None:
    """Register a canonical model. Uses model.VERSION as official version."""
    op_code = getattr(model, "OPERATION_CODE", "").strip().upper()
    version = getattr(model, "VERSION", "1.0").strip()
    if not op_code:
        return
    if op_code not in _REGISTRY:
        _REGISTRY[op_code] = {}
    _REGISTRY[op_code][version] = model
    # Build alias map
    aliases = getattr(model, "VERSION_ALIASES", [])
    if op_code not in _ALIASES:
        _ALIASES[op_code] = {}
    for a in aliases:
        if isinstance(a, str) and a.strip():
            _ALIASES[op_code][a.strip().lower()] = version


def _version_sort_key(v: str) -> tuple[int, int]:
    """Sort versions: 1.0 < 2.0. Parses major.minor."""
    parts = v.replace("v", "").split(".")
    major = int(parts[0]) if parts and parts[0].isdigit() else 0
    minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    return (major, minor)


def resolve_version(operation_code: str, version: str | None) -> str | None:
    """Resolve version or alias to official version string.

    Args:
        operation_code: e.g. GET_VERIFY_MEMBER_ELIGIBILITY
        version: e.g. v1 or 1.0. If None, returns latest official version.

    Returns:
        Official version string (e.g. "1.0") or None if not found.
    """
    _ensure_loaded()
    op_code = (operation_code or "").strip().upper()
    if not op_code or op_code not in _REGISTRY:
        return None
    versions = _REGISTRY[op_code]
    ver_in = (version or "").strip() or None
    if not ver_in:
        return max(versions.keys(), key=_version_sort_key)
    ver_lower = ver_in.lower()
    if ver_lower in versions:
        return ver_lower
    if op_code in _ALIASES and ver_lower in _ALIASES[op_code]:
        return _ALIASES[op_code][ver_lower]
    return None


def list_operations() -> list[dict[str, Any]]:
    """List all registered canonical operations with normalized metadata.

    Returns:
        [ { operationCode, latestVersion, title, description, versions }, ... ]
    """
    _ensure_loaded()
    items: list[dict[str, Any]] = []
    for op_code, versions in sorted(_REGISTRY.items()):
        latest = max(versions.keys(), key=_version_sort_key)
        model = versions[latest]
        item: dict[str, Any] = {
            "operationCode": op_code,
            "latestVersion": latest,
            "versions": sorted(versions.keys(), key=_version_sort_key),
        }
        if getattr(model, "TITLE", None) is not None:
            item["title"] = getattr(model, "TITLE", "")
        if getattr(model, "DESCRIPTION", None) is not None:
            item["description"] = getattr(model, "DESCRIPTION", "")
        items.append(item)
    return items


def get_operation(operation_code: str, version: str | None = None) -> dict[str, Any] | None:
    """Get operation details: schemas, examples, metadata.

    Args:
        operation_code: e.g. GET_VERIFY_MEMBER_ELIGIBILITY
        version: e.g. v1 or 1.0. If None, uses latest.

    Returns:
        {
            operationCode,
            version,
            title,
            description,
            requestPayloadSchema,
            responsePayloadSchema,
            examples: { request, response },
            versionAliases (optional),
        }
        or None if not found.
    """
    _ensure_loaded()
    resolved = resolve_version(operation_code, version)
    if resolved is None:
        return None
    op_code = (operation_code or "").strip().upper()
    model = _REGISTRY[op_code][resolved]
    versions = _REGISTRY[op_code]
    latest = max(versions.keys(), key=_version_sort_key)
    req_schema = getattr(model, "REQUEST_SCHEMA", {})
    resp_schema = getattr(model, "RESPONSE_SCHEMA", {})
    example_req = getattr(model, "EXAMPLE_REQUEST", {})
    example_resp = getattr(model, "EXAMPLE_RESPONSE", {})
    example_req_env = getattr(model, "EXAMPLE_REQUEST_ENVELOPE", None)
    example_resp_env = getattr(model, "EXAMPLE_RESPONSE_ENVELOPE", None)
    examples: dict[str, Any] = {"request": example_req, "response": example_resp}
    if example_req_env is not None:
        examples["requestEnvelope"] = example_req_env
    if example_resp_env is not None:
        examples["responseEnvelope"] = example_resp_env
    result: dict[str, Any] = {
        "operationCode": op_code,
        "version": resolved,
        "latestVersion": latest,
        "requestPayloadSchema": req_schema,
        "responsePayloadSchema": resp_schema,
        "examples": examples,
    }
    title = getattr(model, "TITLE", None)
    if title is not None:
        result["title"] = title
    desc = getattr(model, "DESCRIPTION", None)
    if desc is not None:
        result["description"] = desc
    aliases = getattr(model, "VERSION_ALIASES", [])
    if aliases:
        result["versionAliases"] = list(aliases)
    return result
