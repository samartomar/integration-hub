"""Consistent JSON response structure for API Gateway."""

from __future__ import annotations

import json
from typing import Any


def success(status_code: int, data: dict[str, Any] | list[Any]) -> dict[str, Any]:
    """Build success response with data payload."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"data": data}, default=str),
    }


def no_content() -> dict[str, Any]:
    """Build 204 No Content response."""
    return {
        "statusCode": 204,
        "headers": {"Content-Type": "application/json"},
        "body": "",
    }


def error(status_code: int, code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build error response with canonical structure."""
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
        },
    }
    if details:
        payload["error"]["details"] = details
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload, default=str),
    }
