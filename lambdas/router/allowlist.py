"""Allowlist enforcement layer - enforce_allowlist."""

from __future__ import annotations


def enforce_allowlist(
    source_vendor: str,
    target_vendor: str,
    operation: str,
) -> None:
    """
    Enforce vendor_operation_allowlist: ensure (source,target,operation) is permitted.

    Placeholder: no-op. Will query control_plane.vendor_operation_allowlist
    when implemented. Raises ValueError if not allowed.
    """
    _ = source_vendor, target_vendor, operation  # Used when implemented
