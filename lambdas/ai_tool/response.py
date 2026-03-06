"""Structured response format."""

from __future__ import annotations

import json
from typing import Any


def success(body: dict[str, Any]) -> dict[str, Any]:
    """Build success response with structured format."""
    payload: dict[str, Any] = {
        "status": "OK",
        "message": "Integration executed successfully",
        "missingFields": [],
        "violations": [],
        "executeResult": body,
    }
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload, default=str),
    }


def needs_input(
    message: str,
    violations: list[dict[str, str]],
    required: list[str] | None = None,
) -> dict[str, Any]:
    """Build NEEDS_INPUT response for schema validation failures."""
    payload: dict[str, Any] = {
        "status": "NEEDS_INPUT",
        "message": message,
        "missingFields": required if required is not None else [],
        "violations": violations,
        "executeResult": None,
    }
    if required is not None:
        payload["required"] = required
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload, default=str),
    }


def unknown_operation(operation_code: str) -> dict[str, Any]:
    """Build UNKNOWN_OPERATION error when no active contract found."""
    payload: dict[str, Any] = {
        "status": "ERROR",
        "message": f"No active contract found for {operation_code}",
        "missingFields": [],
        "violations": [],
        "error": {
            "code": "UNKNOWN_OPERATION",
            "message": f"No active contract found for {operation_code}",
        },
    }
    return {
        "statusCode": 404,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload, default=str),
    }


def error(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    violations: list[str] | list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build structured error response. Violations at error.violations (top-level envelope)."""
    payload: dict[str, Any] = {
        "status": "ERROR",
        "message": message,
        "missingFields": [],
        "violations": [],
        "executeResult": None,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if violations is not None:
        payload["error"]["violations"] = violations
    if details:
        payload["error"]["details"] = details
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload, default=str),
    }
