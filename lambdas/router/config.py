"""Vendor config layer - load_vendor_config."""

from __future__ import annotations

from typing import Any


def load_vendor_config(
    source_vendor: str,
    target_vendor: str,
    operation: str,
) -> dict[str, Any]:
    """
    Load vendor and operation configuration for the given routing parameters.

    Placeholder: returns empty config. Will query control_plane.vendors,
    control_plane.operations when implemented.
    """
    _ = source_vendor, target_vendor, operation  # Used when implemented
    return {}
