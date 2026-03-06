"""Transaction logging layer - log_transaction."""

from __future__ import annotations

from typing import Any


def log_transaction(
    transaction_id: str,
    correlation_id: str,
    envelope: dict[str, Any],
    response: dict[str, Any],
) -> None:
    """
    Log transaction to audit/data plane for compliance and replay.

    Placeholder: no-op. Will insert into data_plane.transactions when implemented.
    """
    _ = transaction_id, correlation_id, envelope, response  # Used when implemented
