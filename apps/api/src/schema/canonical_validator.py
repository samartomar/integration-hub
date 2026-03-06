"""Canonical payload and envelope validation.

Uses canonical_registry for schema lookup and version alias resolution.
Raises jsonschema.ValidationError on validation failure.
"""

from __future__ import annotations

from typing import Any

try:
    import jsonschema
except ImportError:
    jsonschema = None  # type: ignore[assignment]


def _require_jsonschema() -> None:
    if jsonschema is None:
        raise ImportError("jsonschema is required for canonical validation")


def validate_request(operation_code: str, payload: dict[str, Any], version: str | None = None) -> None:
    """Validate request payload against canonical request schema.

    Uses canonical_registry for schema lookup. Version alias (e.g. v1) resolves to official version.
    Raises jsonschema.ValidationError on failure.
    """
    _require_jsonschema()
    from schema.canonical_registry import get_operation

    op = get_operation(operation_code, version)
    if op is None:
        raise jsonschema.ValidationError(f"Operation '{operation_code}' not found")
    schema = op.get("requestPayloadSchema") or {}
    if schema:
        jsonschema.validate(instance=payload, schema=schema)


def validate_response(operation_code: str, payload: dict[str, Any], version: str | None = None) -> None:
    """Validate response payload against canonical response schema.

    Uses canonical_registry for schema lookup. Version alias resolution applies.
    Raises jsonschema.ValidationError on failure.
    """
    _require_jsonschema()
    from schema.canonical_registry import get_operation

    op = get_operation(operation_code, version)
    if op is None:
        raise jsonschema.ValidationError(f"Operation '{operation_code}' not found")
    schema = op.get("responsePayloadSchema") or {}
    if schema:
        jsonschema.validate(instance=payload, schema=schema)


def validate_envelope(envelope: dict[str, Any]) -> None:
    """Validate envelope shape: operationCode, version, direction, correlationId, timestamp, context, payload.

    Raises jsonschema.ValidationError on failure.
    """
    _require_jsonschema()
    from schema.canonical_envelope import ENVELOPE_SCHEMA

    jsonschema.validate(instance=envelope, schema=ENVELOPE_SCHEMA)


def validate_request_envelope(
    operation_code: str, envelope: dict[str, Any], version: str | None = None
) -> None:
    """Validate envelope shape and direction=REQUEST, then validate payload against request schema."""
    _require_jsonschema()
    validate_envelope(envelope)
    if envelope.get("direction") != "REQUEST":
        raise jsonschema.ValidationError("Envelope direction must be REQUEST")
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise jsonschema.ValidationError("Envelope payload must be an object")
    validate_request(operation_code, payload, version)


def validate_response_envelope(
    operation_code: str, envelope: dict[str, Any], version: str | None = None
) -> None:
    """Validate envelope shape and direction=RESPONSE, then validate payload against response schema."""
    _require_jsonschema()
    validate_envelope(envelope)
    if envelope.get("direction") != "RESPONSE":
        raise jsonschema.ValidationError("Envelope direction must be RESPONSE")
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise jsonschema.ValidationError("Envelope payload must be an object")
    validate_response(operation_code, payload, version)
