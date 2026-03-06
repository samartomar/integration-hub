"""Consistent JSON response structure."""

from __future__ import annotations

import json
from typing import Any


def success(data: dict[str, Any]) -> dict[str, Any]:
    """Build success response."""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(data, default=str),
    }


def error_response(
    status_code: int, code: str, message: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build error response with canonical structure."""
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details:
        payload["error"]["details"] = details
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload, default=str),
    }
