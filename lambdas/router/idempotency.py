"""Idempotency layer - check_idempotency."""

from __future__ import annotations


def check_idempotency(idempotency_key: str | None) -> None:
    """
    Check idempotency: if key was previously processed, return cached result or raise.

    Placeholder: no-op. Will query data_plane.transactions when implemented.
    Raises ValueError if duplicate idempotency key detected.
    """
    _ = idempotency_key  # Used when implemented
