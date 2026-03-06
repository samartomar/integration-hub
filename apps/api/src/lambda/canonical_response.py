"""Canonical response format for Registry and Audit Lambdas.

Error format:
{
  "transactionId": "<uuid>",
  "correlationId": "<uuid>",
  "error": { "code": "...", "message": "...", "details": {...} }
}

Success format (payload merged at top level):
{
  "transactionId": "<uuid>",
  "correlationId": "<uuid>",
  ...payload
}

For list endpoints, transactionId/correlationId are generated per request (not stored).
"""

from __future__ import annotations

import json
import uuid
from typing import Any


def _new_ids() -> tuple[str, str]:
    """Generate transactionId and correlationId for this request."""
    t = str(uuid.uuid4())
    c = str(uuid.uuid4())
    return t, c


def canonical_error(
    code: str,
    message: str,
    status_code: int = 400,
    details: dict[str, Any] | None = None,
    category: str | None = None,
    retryable: bool | None = None,
) -> dict[str, Any]:
    """Build canonical error response. Generates transactionId/correlationId per request."""
    transaction_id, correlation_id = _new_ids()
    error_obj: dict[str, Any] = {"code": code, "message": message}
    if category is not None:
        error_obj["category"] = category
    if retryable is not None:
        error_obj["retryable"] = retryable
    if details is not None:
        error_obj["details"] = details
    body: dict[str, Any] = {
        "transactionId": transaction_id,
        "correlationId": correlation_id,
        "error": error_obj,
    }
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def canonical_ok(payload: dict[str, Any], status_code: int = 200) -> dict[str, Any]:
    """Build canonical success response. Generates transactionId/correlationId and merges payload."""
    transaction_id, correlation_id = _new_ids()
    body: dict[str, Any] = {
        "transactionId": transaction_id,
        "correlationId": correlation_id,
        **payload,
    }
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def policy_denied_response(decision: Any) -> dict[str, Any]:
    """Convert a policy decision into canonical error envelope."""
    details = {"policy": decision.metadata} if getattr(decision, "metadata", None) else None
    return canonical_error(
        str(getattr(decision, "decision_code", "FORBIDDEN")),
        str(getattr(decision, "message", "Forbidden")),
        status_code=int(getattr(decision, "http_status", 403)),
        details=details,
    )
