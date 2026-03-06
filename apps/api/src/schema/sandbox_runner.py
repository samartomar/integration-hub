"""Sandbox runner - mock-safe helpers for canonical operations.

No DB reads, no external calls, no runtime wiring.
Uses Canon as source of truth.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import jsonschema


def list_sandbox_operations() -> list[dict[str, Any]]:
    """List all sandbox-eligible canonical operations.

    Thin wrapper over canonical_registry.list_operations().
    """
    from schema.canonical_registry import list_operations

    return list_operations()


def get_sandbox_operation(operation_code: str, version: str | None = None) -> dict[str, Any] | None:
    """Get sandbox operation detail: schemas, examples, metadata.

    Thin wrapper over canonical_registry.get_operation().
    """
    from schema.canonical_registry import get_operation

    return get_operation(operation_code, version)


def validate_sandbox_request(
    operation_code: str, payload: dict[str, Any], version: str | None = None
) -> None:
    """Validate request payload against canonical request schema.

    Uses canonical_validator.validate_request().
    Raises jsonschema.ValidationError on failure.
    """
    from schema.canonical_validator import validate_request

    validate_request(operation_code, payload, version)


def build_sandbox_request_envelope(
    operation_code: str,
    payload: dict[str, Any],
    version: str | None = None,
    correlation_id: str | None = None,
    timestamp: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build and validate a canonical request envelope.

    Uses canonical_envelope.build_envelope() with direction=REQUEST.
    Resolves version alias via canonical_registry.
    Validates final envelope via canonical_validator.validate_request_envelope().
    """
    from schema.canonical_envelope import build_envelope
    from schema.canonical_registry import resolve_version
    from schema.canonical_validator import validate_request_envelope

    resolved = resolve_version(operation_code, version)
    if resolved is None:
        raise ValueError(f"Operation '{operation_code}' with version '{version}' not found")
    op_code = (operation_code or "").strip().upper()
    corr = correlation_id or f"corr-sandbox-{uuid.uuid4().hex[:12]}"
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ctx = context if context is not None else {}
    envelope = build_envelope(
        op_code,
        resolved,
        "REQUEST",
        payload,
        correlation_id=corr,
        timestamp=ts,
        context=ctx,
    )
    validate_request_envelope(op_code, envelope, resolved)
    return envelope


def run_mock_sandbox_test(
    operation_code: str,
    payload: dict[str, Any],
    version: str | None = None,
    correlation_id: str | None = None,
    timestamp: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run mock sandbox test: validate payload, build envelopes, return mock result.

    - Validates request payload
    - Builds normalized request envelope
    - Creates mock response envelope using canonical example response
    - Validates response envelope
    - Returns structured sandbox result

    No vendor endpoint is called. No persistence.
    """
    from schema.canonical_envelope import build_envelope
    from schema.canonical_registry import get_operation, resolve_version
    from schema.canonical_validator import validate_request_envelope, validate_response_envelope

    op_code = (operation_code or "").strip().upper()
    resolved = resolve_version(op_code, version)
    if resolved is None:
        return {
            "operationCode": op_code,
            "version": version or "?",
            "mode": "MOCK",
            "valid": False,
            "errors": [
                {
                    "field": "operationCode",
                    "message": f"Operation '{op_code}' with version '{version}' not found in canonical registry",
                }
            ],
        }

    errors: list[dict[str, str]] = []
    request_payload_valid = False
    request_envelope_valid = False
    response_envelope_valid = False
    request_envelope: dict[str, Any] = {}
    response_envelope: dict[str, Any] = {}

    # 1. Validate request payload
    try:
        validate_sandbox_request(op_code, payload, resolved)
        request_payload_valid = True
    except jsonschema.ValidationError as e:
        path = ".".join(str(p) for p in e.path) if e.path else "payload"
        errors.append({"field": path, "message": e.message or str(e)})

    # 2. Build and validate request envelope (only if payload valid)
    if request_payload_valid:
        try:
            corr = correlation_id or f"corr-sandbox-{uuid.uuid4().hex[:12]}"
            ts = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            ctx = context if context is not None else {}
            request_envelope = build_sandbox_request_envelope(
                op_code, payload, resolved, correlation_id=corr, timestamp=ts, context=ctx
            )
            validate_request_envelope(op_code, request_envelope, resolved)
            request_envelope_valid = True
        except (jsonschema.ValidationError, ValueError) as e:
            errors.append({"field": "requestEnvelope", "message": str(e)})

    # 3. Build mock response envelope from canonical example
    if request_envelope_valid:
        op = get_operation(op_code, resolved)
        if op and op.get("examples", {}).get("response"):
            example_response = dict(op["examples"]["response"])
            corr = request_envelope.get("correlationId", f"corr-sandbox-{uuid.uuid4().hex[:12]}")
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            response_envelope = build_envelope(
                op_code,
                resolved,
                "RESPONSE",
                example_response,
                correlation_id=corr,
                timestamp=ts,
                context=context or {},
            )
            try:
                validate_response_envelope(op_code, response_envelope, resolved)
                response_envelope_valid = True
            except jsonschema.ValidationError as e:
                errors.append({"field": "responseEnvelope", "message": str(e)})
        else:
            errors.append({"field": "responseEnvelope", "message": "No example response in registry"})

    valid = request_payload_valid and request_envelope_valid and response_envelope_valid

    result: dict[str, Any] = {
        "operationCode": op_code,
        "version": resolved,
        "mode": "MOCK",
        "valid": valid,
        "requestPayloadValid": request_payload_valid,
        "requestEnvelopeValid": request_envelope_valid,
        "responseEnvelopeValid": response_envelope_valid,
    }

    if valid:
        result["requestEnvelope"] = request_envelope
        result["responseEnvelope"] = response_envelope
        result["notes"] = [
            "Mock sandbox execution only. No vendor endpoint was called.",
        ]
    else:
        result["errors"] = errors

    return result
