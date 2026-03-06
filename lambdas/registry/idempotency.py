"""Idempotency check for create operations."""

from __future__ import annotations


def check_idempotency(idempotency_key: str | None) -> None:
    """
    Check if request with this idempotency key was already processed.
    Placeholder: no-op. Will query data store when implemented.
    Raises ValueError if duplicate key (already processed).
    """
    if idempotency_key is None or not idempotency_key.strip():
        return
    _ = idempotency_key  # Used when implemented


def get_idempotency_key_from_event(event: dict[str, object]) -> str | None:
    """Extract Idempotency-Key or X-Idempotency-Key from API Gateway event."""
    headers = event.get("headers") or {}
    if isinstance(headers, dict):
        key = headers.get("Idempotency-Key") or headers.get("idempotency-key")
        if key:
            return str(key).strip()
        key = headers.get("X-Idempotency-Key") or headers.get("x-idempotency-key")
        if key:
            return str(key).strip()
    return None
