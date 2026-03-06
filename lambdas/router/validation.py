"""Request validation layer - validate_request."""

from __future__ import annotations

import json
from typing import Any


def validate_request(event: dict[str, Any]) -> dict[str, Any]:
    """
    Validate and parse API Gateway proxy event into a canonical request payload.

    Returns dict with: source_vendor, target_vendor, operation, idempotency_key.
    Raises ValueError with a clear message on validation failure.
    """
    body_raw: str = event.get("body") or "{}"
    try:
        payload: dict[str, Any] = json.loads(body_raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON body: {e}") from e

    source_vendor: str | None = payload.get("sourceVendor")
    target_vendor: str | None = payload.get("targetVendor")
    operation: str | None = payload.get("operation")
    idempotency_key: str | None = payload.get("idempotencyKey")
    request_type: str | None = payload.get("requestType")
    callback_url: str | None = payload.get("callbackUrl")

    if not source_vendor or not isinstance(source_vendor, str):
        raise ValueError("sourceVendor is required and must be a non-empty string")
    if not target_vendor or not isinstance(target_vendor, str):
        raise ValueError("targetVendor is required and must be a non-empty string")
    if not operation or not isinstance(operation, str):
        raise ValueError("operation is required and must be a non-empty string")
    if idempotency_key is not None and not isinstance(idempotency_key, str):
        raise ValueError("idempotencyKey must be a string when provided")
    if request_type is not None and request_type not in ("SYNC", "ASYNC"):
        raise ValueError("requestType must be SYNC or ASYNC")
    if callback_url is not None and not isinstance(callback_url, str):
        raise ValueError("callbackUrl must be a string when provided")

    return {
        "source_vendor": source_vendor.strip(),
        "target_vendor": target_vendor.strip(),
        "operation": operation.strip(),
        "idempotency_key": idempotency_key.strip() if idempotency_key else None,
        "request_type": (request_type or "SYNC").upper(),
        "callback_url": callback_url.strip() if callback_url else None,
    }
