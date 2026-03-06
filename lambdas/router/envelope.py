"""Canonical envelope layer - build_canonical_envelope."""

from __future__ import annotations

from typing import Any


def build_canonical_envelope(
    source_vendor: str,
    target_vendor: str,
    operation: str,
    correlation_id: str,
    *,
    idempotency_key: str | None = None,
    request_type: str = "SYNC",
    callback_url: str | None = None,
) -> dict[str, Any]:
    """
    Build canonical request envelope for downstream invocation.
    """
    envelope: dict[str, Any] = {
        "sourceVendor": source_vendor,
        "targetVendor": target_vendor,
        "operation": operation,
        "requestType": request_type,
        "correlationId": correlation_id,
    }
    if idempotency_key is not None:
        envelope["idempotencyKey"] = idempotency_key
    if callback_url is not None:
        envelope["callbackUrl"] = callback_url
    return envelope
