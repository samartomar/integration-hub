"""Canonical envelope for Integration Hub API."""

from __future__ import annotations

from typing import Any


def generate_idempotency_key_if_missing(idempotency_key: str | None) -> str | None:
    """Return idempotency_key if provided, else None (Hub accepts optional)."""
    if idempotency_key is not None and idempotency_key.strip():
        return idempotency_key.strip()
    return None


def build_canonical_envelope(
    source_vendor: str,
    target_vendor: str,
    operation: str,
    idempotency_key: str | None,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """
    Build request body for Integration Hub API POST /v1/integrations/execute.
    sourceVendor is derived from JWT (not in body).
    Body: { targetVendor, operation, idempotencyKey?, parameters }
    """
    envelope: dict[str, Any] = {
        "targetVendor": target_vendor,
        "operation": operation,
        "parameters": parameters,
    }
    if idempotency_key is not None:
        envelope["idempotencyKey"] = idempotency_key
    return envelope
