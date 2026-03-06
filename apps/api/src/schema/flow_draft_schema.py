"""Flow draft schema - minimal canonical-driven flow configuration.

Read-only validation and normalization. No persistence.
"""

from __future__ import annotations

from typing import Any


ALLOWED_TRIGGER_TYPES = frozenset({"MANUAL", "API"})
ALLOWED_MAPPING_MODES = frozenset({"CANONICAL_FIRST"})


class FlowDraftValidationError(Exception):
    """Raised when flow draft validation fails."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


def validate_flow_draft(payload: dict[str, Any]) -> None:
    """Validate flow draft structure and references.

    Raises:
        FlowDraftValidationError: On validation failure.
    """
    if not isinstance(payload, dict):
        raise FlowDraftValidationError("Payload must be an object", field=None)

    name = payload.get("name")
    if not name or not str(name).strip():
        raise FlowDraftValidationError("name is required and must be non-empty", field="name")

    operation_code = (payload.get("operationCode") or payload.get("operation_code") or "").strip()
    if not operation_code:
        raise FlowDraftValidationError("operationCode is required", field="operationCode")

    version = (payload.get("version") or "").strip()
    if not version:
        raise FlowDraftValidationError("version is required", field="version")

    source_vendor = (payload.get("sourceVendor") or payload.get("source_vendor") or "").strip()
    if not source_vendor:
        raise FlowDraftValidationError("sourceVendor is required", field="sourceVendor")

    target_vendor = (payload.get("targetVendor") or payload.get("target_vendor") or "").strip()
    if not target_vendor:
        raise FlowDraftValidationError("targetVendor is required", field="targetVendor")

    trigger = payload.get("trigger")
    if not isinstance(trigger, dict):
        raise FlowDraftValidationError("trigger is required and must be an object", field="trigger")

    trigger_type = (trigger.get("type") or "").strip().upper()
    if trigger_type not in ALLOWED_TRIGGER_TYPES:
        raise FlowDraftValidationError(
            f"trigger.type must be one of: {', '.join(sorted(ALLOWED_TRIGGER_TYPES))}",
            field="trigger.type",
        )

    mapping_mode = (payload.get("mappingMode") or payload.get("mapping_mode") or "").strip().upper()
    if mapping_mode not in ALLOWED_MAPPING_MODES:
        raise FlowDraftValidationError(
            f"mappingMode must be one of: {', '.join(sorted(ALLOWED_MAPPING_MODES))}",
            field="mappingMode",
        )

    # operationCode and version must exist in canonical_registry
    from schema.canonical_registry import resolve_version

    resolved = resolve_version(operation_code.upper(), version)
    if resolved is None:
        raise FlowDraftValidationError(
            f"operationCode '{operation_code}' with version '{version}' not found in canonical registry",
            field="operationCode",
        )


def normalize_flow_draft(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize flow draft. Resolves version alias to official version.

    Returns:
        Normalized draft with camelCase keys, trimmed strings, resolved version.
    """
    validate_flow_draft(payload)

    from schema.canonical_registry import resolve_version

    operation_code = (payload.get("operationCode") or payload.get("operation_code") or "").strip().upper()
    version_in = (payload.get("version") or "").strip()
    resolved_version = resolve_version(operation_code, version_in) or version_in

    name = str(payload.get("name") or "").strip()
    source_vendor = str(payload.get("sourceVendor") or payload.get("source_vendor") or "").strip()
    target_vendor = str(payload.get("targetVendor") or payload.get("target_vendor") or "").strip()
    trigger = payload.get("trigger") or {}
    trigger_type = (trigger.get("type") or "MANUAL").strip().upper()
    mapping_mode = (
        payload.get("mappingMode") or payload.get("mapping_mode") or "CANONICAL_FIRST"
    ).strip().upper()
    notes = str(payload.get("notes") or "").strip()

    return {
        "name": name,
        "operationCode": operation_code,
        "version": resolved_version,
        "sourceVendor": source_vendor,
        "targetVendor": target_vendor,
        "trigger": {"type": trigger_type},
        "mappingMode": mapping_mode,
        "notes": notes if notes else None,
    }
