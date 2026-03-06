"""
Direction vocabulary: OUTBOUND / INBOUND only.

Single source of truth for flow_direction semantics.
Replace any language translations (e.g. "I send", "Provider receives") with raw OUTBOUND/INBOUND.

Canonical: operations.direction_policy
Vendor: vendor_supported_operations.flow_direction ∈ { OUTBOUND, INBOUND }
"""

from __future__ import annotations

DIR_OUTBOUND = "OUTBOUND"
DIR_INBOUND = "INBOUND"


def is_outbound(flow_direction: str | None) -> bool:
    """True if flow_direction is OUTBOUND."""
    return (flow_direction or "").strip().upper() == DIR_OUTBOUND


def is_inbound(flow_direction: str | None) -> bool:
    """True if flow_direction is INBOUND."""
    return (flow_direction or "").strip().upper() == DIR_INBOUND


def derive_vendor_flow_by_role(direction_policy: str | None, vendor_role: str) -> str:
    """
    Derive flow_direction from operation direction_policy and vendor role.

    vendor_role: "provider" (receives call) or "caller" (sends call).
    direction_policy: PROVIDER_RECEIVES_ONLY, TWO_WAY, or legacy mapped values.

    PROVIDER_RECEIVES_ONLY: provider=INBOUND, caller=OUTBOUND.
    TWO_WAY: default OUTBOUND for backward compatibility; either direction possible.
    """
    if not direction_policy:
        return DIR_OUTBOUND
    policy = direction_policy.strip().upper()
    role = (vendor_role or "").strip().lower()
    if policy == "PROVIDER_RECEIVES_ONLY":
        return DIR_INBOUND if role == "provider" else DIR_OUTBOUND
    if policy in ("TWO_WAY", "CALLER_SENDS_ONLY", "SERVICE_OUTBOUND_ONLY"):
        return DIR_OUTBOUND
    return DIR_OUTBOUND


def derive_vendor_flow(
    source_vendor: str,
    target_vendor: str,
    operation_direction_policy: str | None,
    *,
    for_vendor: str | None = None,
) -> str:
    """
    Derive flow_direction for a vendor in a source->target call.

    When for_vendor matches target: returns flow from provider perspective (INBOUND).
    When for_vendor matches source or not provided: returns flow from caller perspective (OUTBOUND).
    When for_vendor is None: returns flow for target (provider) = INBOUND for provider-receives flows.

    Use for endpoint/contract resolution: target's perspective = INBOUND, source's = OUTBOUND.
    """
    role = "provider" if (for_vendor or "").strip().upper() == (target_vendor or "").strip().upper() else "caller"
    return derive_vendor_flow_by_role(operation_direction_policy, role)
