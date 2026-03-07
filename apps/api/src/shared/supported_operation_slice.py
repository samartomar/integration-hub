"""Supported canonical operation slice – explicit product cutover scope.

This module defines the currently cutover-supported operations and vendor pair.
It drives UI/product routing decisions. Not a fake scaffold list; this is the
explicit product cutover scope for the canonical-first workflow.

Supported slice:
- Operations: GET_VERIFY_MEMBER_ELIGIBILITY, GET_MEMBER_ACCUMULATORS
- Vendor pair: LH001 -> LH002 (source -> target)
"""

from __future__ import annotations

# Supported operations (production-mature canonical-first flow)
SUPPORTED_OPERATIONS = frozenset({
    "GET_VERIFY_MEMBER_ELIGIBILITY",
    "GET_MEMBER_ACCUMULATORS",
})

# Supported vendor pair (source, target)
SUPPORTED_SOURCE_VENDOR = "LH001"
SUPPORTED_TARGET_VENDOR = "LH002"


def is_supported_canonical_slice(
    operation_code: str,
    source_vendor: str | None = None,
    target_vendor: str | None = None,
) -> bool:
    """Check if the operation (and optionally vendor pair) is in the supported slice.

    When source_vendor and target_vendor are provided, both must match the
    supported pair. When omitted, only operation_code is checked.

    Args:
        operation_code: Operation code (e.g. GET_VERIFY_MEMBER_ELIGIBILITY).
        source_vendor: Optional source vendor code.
        target_vendor: Optional target vendor code.

    Returns:
        True if in supported slice.
    """
    op = (operation_code or "").strip().upper()
    if op not in SUPPORTED_OPERATIONS:
        return False
    if source_vendor is None and target_vendor is None:
        return True
    src = (source_vendor or "").strip().upper()
    tgt = (target_vendor or "").strip().upper()
    return src == SUPPORTED_SOURCE_VENDOR and tgt == SUPPORTED_TARGET_VENDOR


def list_supported_canonical_operations() -> list[str]:
    """Return the list of supported operation codes for the canonical-first flow."""
    return sorted(SUPPORTED_OPERATIONS)


def get_supported_vendor_pair() -> tuple[str, str]:
    """Return (source_vendor, target_vendor) for the supported slice."""
    return (SUPPORTED_SOURCE_VENDOR, SUPPORTED_TARGET_VENDOR)
