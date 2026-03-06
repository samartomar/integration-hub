"""Response building layer - build_response and canonical error structure."""

from __future__ import annotations

import json
import uuid
from typing import Any


def _canonical_error(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build canonical error structure for all failure responses."""
    error: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
        },
    }
    if details:
        error["error"]["details"] = details
    return error


def build_error_response(
    status_code: int,
    error_code: str,
    message: str,
    details: dict[str, Any] | None = None,
    transaction_id: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """
    Build API Gateway response with canonical error structure.
    """
    body: dict[str, Any] = _canonical_error(error_code, message, details)
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if transaction_id:
        headers["X-Transaction-Id"] = transaction_id
    if correlation_id:
        headers["X-Correlation-Id"] = correlation_id
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body, default=str),
    }


def build_response(
    transaction_id: str,
    correlation_id: str,
    envelope: dict[str, Any],
    downstream_response: dict[str, Any],
) -> dict[str, Any]:
    """
    Build API Gateway success response from downstream result.
    """
    body: dict[str, Any] = {
        "transactionId": transaction_id,
        "correlationId": correlation_id,
        **envelope,
        **downstream_response,
    }
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "X-Transaction-Id": transaction_id,
            "X-Correlation-Id": correlation_id,
        },
        "body": json.dumps(body, default=str),
    }


def generate_ids() -> tuple[str, str]:
    """Generate transaction_id and correlation_id."""
    return str(uuid.uuid4()), str(uuid.uuid4())
