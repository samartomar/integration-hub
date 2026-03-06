"""Mapping direction constants for vendor_operation_mappings."""

# Source request: vendor-specific params -> canonical request (optional)
TO_CANONICAL_REQUEST = "TO_CANONICAL_REQUEST"
# Response: canonical -> source vendor response format
FROM_CANONICAL_RESPONSE = "FROM_CANONICAL_RESPONSE"

MAPPING_DIRECTIONS = frozenset({
    "TO_CANONICAL",
    "FROM_CANONICAL",
    "TO_CANONICAL_RESPONSE",
    "FROM_CANONICAL_RESPONSE",
    TO_CANONICAL_REQUEST,
})


def is_valid_mapping_direction(direction: str) -> bool:
    """Return True if direction is in allowed list."""
    return str(direction).strip().upper() in MAPPING_DIRECTIONS
