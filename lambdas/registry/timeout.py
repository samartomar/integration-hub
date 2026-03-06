"""Timeout handling - ensure sufficient Lambda time before long operations."""

from __future__ import annotations

MIN_REMAINING_MS = 3000


def ensure_sufficient_time(context: object) -> None:
    """Raise TimeoutError if insufficient time remains."""
    if context is None:
        return
    remaining = getattr(context, "get_remaining_time_in_millis", None)
    if callable(remaining):
        ms = remaining()
        if ms is not None and ms < MIN_REMAINING_MS:
            raise TimeoutError(f"Insufficient time remaining: {ms}ms")
