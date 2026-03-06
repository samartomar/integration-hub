"""
Canonical pass-through mapping readiness helper.

Pure logic for determining if mapping is configured for a direction.
Shared by registry_lambda and vendor_registry_lambda.
"""

from __future__ import annotations


def _has_request_mapping_for_direction(
    present_directions: set[str], flow_direction: str
) -> bool:
    """True if active request mapping exists for this flow direction.

    Direction pairs (per baseline):
    - OUTBOUND (provider/target: platform calls vendor): request=FROM_CANONICAL, response=TO_CANONICAL_RESPONSE
    - INBOUND (source: vendor sends to platform): request=TO_CANONICAL, response=FROM_CANONICAL_RESPONSE
    """
    outbound = flow_direction.upper() == "OUTBOUND"
    want = {"FROM_CANONICAL"} if outbound else {"TO_CANONICAL", "TO_CANONICAL_REQUEST"}
    return bool(present_directions & want)


def _has_response_mapping_for_direction(
    present_directions: set[str], flow_direction: str
) -> bool:
    """True if active response mapping exists for this flow direction."""
    outbound = flow_direction.upper() == "OUTBOUND"
    want = "TO_CANONICAL_RESPONSE" if outbound else "FROM_CANONICAL_RESPONSE"
    return want in present_directions


def is_mapping_configured_for_direction(
    *,
    present_directions: set[str],
    has_vendor_contract: bool,
    flow_direction: str,
) -> tuple[bool, bool, bool]:
    """
    Returns (mapping_configured, uses_canonical_request, uses_canonical_response).

    - mapping_configured: True if mapping requirements are satisfied.
    - uses_canonical_request: True if configured purely via canonical pass-through for request.
    - uses_canonical_response: True if configured purely via canonical pass-through for response.
    """
    has_req = _has_request_mapping_for_direction(present_directions, flow_direction)
    has_resp = _has_response_mapping_for_direction(present_directions, flow_direction)

    if has_req and has_resp:
        return True, False, False

    if has_vendor_contract:
        return False, False, False

    uses_canonical_request = not has_req
    uses_canonical_response = not has_resp
    return True, uses_canonical_request, uses_canonical_response
