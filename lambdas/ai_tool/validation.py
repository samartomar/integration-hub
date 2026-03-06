"""Strict JSON schema and control_plane validation (V2 schema: vendor_code, operation_code)."""

from __future__ import annotations

from typing import Any

import jsonschema
from db import execute_one, get_connection
from psycopg2 import sql

SCHEMA = "control_plane"

# Strict JSON schema for ExecuteIntegration input (generic, no per-operation fields)
EXECUTE_INTEGRATION_SCHEMA = {
    "type": "object",
    "properties": {
        "sourceVendor": {"type": "string", "minLength": 1, "maxLength": 64},
        "targetVendor": {"type": "string", "minLength": 1, "maxLength": 64},
        "operation": {"type": "string", "minLength": 1, "maxLength": 64},
        "operationCode": {"type": "string", "minLength": 1, "maxLength": 64},  # legacy alias
        "canonicalVersion": {"type": "string", "minLength": 1, "maxLength": 32},
        "parameters": {"type": "object"},
        "idempotencyKey": {"type": "string", "minLength": 1, "maxLength": 256},
    },
    "required": ["sourceVendor", "targetVendor", "operation", "parameters"],
    "additionalProperties": False,
}


class ValidationError(Exception):
    """Structured validation error with code."""

    def __init__(self, message: str, code: str = "VALIDATION_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


def validate_input_schema(body: Any) -> dict[str, Any]:
    """
    Strict JSON schema validation for ExecuteIntegration input.
    Returns {source_vendor, target_vendor, operation, canonical_version, parameters, idempotency_key}.
    Raises ValidationError on failure.
    """
    if not isinstance(body, dict):
        raise ValidationError("Input must be a JSON object", "INVALID_INPUT")

    # Legacy: map operationCode -> operation so schema validation passes
    if body.get("operationCode") and not body.get("operation"):
        body = {**body, "operation": body["operationCode"]}

    try:
        jsonschema.validate(instance=body, schema=EXECUTE_INTEGRATION_SCHEMA)
    except jsonschema.ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path) if e.absolute_path else "root"
        msg = getattr(e, "message", None) or str(e)
        raise ValidationError(f"Schema validation failed at {path}: {msg}", "SCHEMA_VALIDATION") from e

    source = body["sourceVendor"].strip()
    target = body["targetVendor"].strip()
    operation = (body.get("operation") or body.get("operationCode") or "").strip()
    if not operation:
        raise ValidationError("operation is required", "VALIDATION_ERROR")
    canonical_version = (body.get("canonicalVersion") or "v1").strip() or "v1"
    parameters = body["parameters"]
    idempotency_key = body.get("idempotencyKey")
    idempotency_key = idempotency_key.strip() if idempotency_key else None

    return {
        "source_vendor": source,
        "target_vendor": target,
        "operation": operation,
        "canonical_version": canonical_version,
        "parameters": parameters,
        "idempotency_key": idempotency_key,
    }


def validate_vendor_exists_and_active(vendor_code: str) -> None:
    """Validate vendor exists and is active. Raises ValidationError if not."""
    with get_connection() as conn:
        q = sql.SQL(
            "SELECT 1 FROM {}.vendors WHERE vendor_code = %s AND COALESCE(is_active, true)"
        ).format(sql.Identifier(SCHEMA))
        row = execute_one(conn, q, (vendor_code,))
    if not row:
        raise ValidationError(f"Vendor not found or inactive: {vendor_code}", "VENDOR_NOT_FOUND")


def validate_operation_exists_and_active(operation_code: str) -> None:
    """Validate operation exists and is active. Raises ValidationError if not."""
    with get_connection() as conn:
        q = sql.SQL(
            "SELECT 1 FROM {}.operations WHERE operation_code = %s AND COALESCE(is_active, true)"
        ).format(sql.Identifier(SCHEMA))
        row = execute_one(conn, q, (operation_code,))
    if not row:
        raise ValidationError(f"Operation not found or inactive: {operation_code}", "OPERATION_NOT_FOUND")


def fetch_request_schema(operation_code: str, canonical_version: str) -> dict[str, Any] | None:
    """
    Fetch request_schema from control_plane.operation_contracts.
    Returns request_schema dict or None if no active contract found.
    """
    with get_connection() as conn:
        q = sql.SQL(
            """
            SELECT request_schema
            FROM {}.operation_contracts
            WHERE operation_code = %s
              AND canonical_version = %s
              AND is_active = true
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 1
            """
        ).format(sql.Identifier(SCHEMA))
        row = execute_one(conn, q, (operation_code, canonical_version))
    if not row or not row.get("request_schema"):
        return None
    schema = row["request_schema"]
    return schema if isinstance(schema, dict) else None


def get_operation_canonical_version(operation_code: str) -> str:
    """Get canonical_version from operations table. Defaults to 'v1' if null."""
    with get_connection() as conn:
        q = sql.SQL(
            "SELECT canonical_version FROM {}.operations WHERE operation_code = %s AND COALESCE(is_active, true)"
        ).format(sql.Identifier(SCHEMA))
        row = execute_one(conn, q, (operation_code,))
    if not row or not row.get("canonical_version"):
        return "v1"
    return str(row["canonical_version"]).strip() or "v1"


def validate_parameters_schema(
    parameters: dict[str, Any],
    request_schema: dict[str, Any],
) -> tuple[list[dict[str, str]], list[str] | None]:
    """
    Validate parameters against request_schema using jsonschema.
    Returns (violations, required).
    violations: list of {path, message}
    required: list of required property names from schema, or None if not available
    """
    violations: list[dict[str, str]] = []

    def collect(err: jsonschema.ValidationError) -> None:
        path = ".".join(str(p) for p in err.absolute_path) if err.absolute_path else ""
        violations.append({"path": path or "parameters", "message": err.message})

    try:
        jsonschema.validate(instance=parameters, schema=request_schema)
        return ([], None)
    except jsonschema.ValidationError as e:
        for err in e.context or [e]:
            collect(err)
        if not violations:
            collect(e)
        required = None
        if isinstance(request_schema.get("required"), list):
            required = list(request_schema["required"])
        return (violations, required)


def validate_allowlist(
    source_vendor_code: str,
    target_vendor_code: str,
    operation_code: str,
) -> None:
    """
    Validate allowlist permits (source_vendor_code, target_vendor_code, operation_code).
    Uses is_any_source / is_any_target for wildcards (no '*' or HUB).
    Raises ValidationError if not permitted.
    """
    with get_connection() as conn:
        q = sql.SQL(
            """
            SELECT 1 FROM {}.vendor_operation_allowlist
            WHERE operation_code = %s
              AND (COALESCE(is_any_source, FALSE) = TRUE OR source_vendor_code = %s)
              AND (COALESCE(is_any_target, FALSE) = TRUE OR target_vendor_code = %s)
            LIMIT 1
            """
        ).format(sql.Identifier(SCHEMA))
        row = execute_one(conn, q, (operation_code, source_vendor_code, target_vendor_code))
    if not row:
        raise ValidationError(
            f"Allowlist violation: {source_vendor_code} -> {target_vendor_code} for {operation_code} not permitted",
            "ALLOWLIST_VIOLATION",
        )
