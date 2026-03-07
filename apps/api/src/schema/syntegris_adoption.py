"""Syntegris adoption classification - deterministic adoption stages.

Combines integration inventory evidence with canonical readiness, mapping readiness,
and release readiness. Classifies each operation/vendor-pair into adoption stages.
No persistence. No runtime mutation. Read-only. Admin-only.
"""

from __future__ import annotations

from typing import Any

from schema.canonical_mapping_engine import get_mapping_definition
from schema.canonical_registry import get_operation
from schema.mapping_onboarding_actions import get_mapping_next_action
from schema.mapping_readiness import get_mapping_readiness
from schema.mapping_release_readiness import (
    _derive_release_readiness_item,
    list_mapping_release_readiness,
)
from shared.supported_operation_slice import is_supported_canonical_slice

ADOPTION_NOTE = "Adoption status is derived from inventory and Syntegris artifacts. No fabrication."

# Adoption statuses
LEGACY_ONLY = "LEGACY_ONLY"
CANON_DEFINED = "CANON_DEFINED"
MAPPING_IN_PROGRESS = "MAPPING_IN_PROGRESS"
CERTIFIED = "CERTIFIED"
RELEASE_READY = "RELEASE_READY"
SYNTEGRIS_READY = "SYNTEGRIS_READY"
BLOCKED = "BLOCKED"


def _normalize_version(version: str | None) -> str:
    """Normalize version to 1.0 format."""
    v = (version or "1.0").strip().replace("v", "")
    if "." not in v:
        v = f"{v}.0" if v.isdigit() else "1.0"
    return v


def _is_supported_slice(operation_code: str, source_vendor: str, target_vendor: str) -> bool:
    """Check if pair is in current supported canonical slice."""
    return is_supported_canonical_slice(operation_code, source_vendor, target_vendor)


def _route_for_action(code: str, prefill: dict[str, Any]) -> str:
    """Map action code to target route."""
    base = "/admin/canonical-mapping-readiness"
    if code == "READY":
        return "/admin/canonical-mapping-readiness"
    if code == "GENERATE_SCAFFOLD":
        return "/admin/canonical-mappings"
    if code == "ADD_FIXTURES":
        return "/admin/canonical-mappings"
    if code == "RUN_CERTIFICATION":
        return "/admin/canonical-mappings"
    if code == "COMPLETE_MAPPING_DEFINITION":
        return "/admin/canonical-mappings"
    if code == "REVIEW_PROMOTION_ARTIFACT":
        return "/admin/canonical-mappings"
    if code == "INVESTIGATE_WARN":
        return "/admin/canonical-mappings"
    return base


def classify_syntegris_adoption(inventory_item: dict[str, Any]) -> dict[str, Any]:
    """Classify adoption status for a single inventory item.

    Args:
        inventory_item: From list_integration_inventory / get_integration_inventory_item.

    Returns:
        {
            operationCode, version, sourceVendor, targetVendor,
            adoptionStatus, inventoryEvidence, syntegrisEvidence,
            nextAction: { code, title, targetRoute },
            notes
        }
    """
    if not isinstance(inventory_item, dict):
        return {
            "operationCode": "",
            "version": "1.0",
            "sourceVendor": "",
            "targetVendor": "",
            "adoptionStatus": BLOCKED,
            "inventoryEvidence": {},
            "syntegrisEvidence": {},
            "nextAction": {"code": "INVESTIGATE", "title": "Invalid item", "targetRoute": "/admin/canonical-mapping-readiness"},
            "notes": ["Invalid inventory item."],
        }

    op = (inventory_item.get("operationCode") or "").strip().upper()
    ver = _normalize_version(inventory_item.get("version"))
    src = (inventory_item.get("sourceVendor") or "").strip().upper()
    tgt = (inventory_item.get("targetVendor") or "").strip().upper()
    inv_evidence = inventory_item.get("inventoryEvidence") or {}
    notes = list(inventory_item.get("notes") or [])

    # Check if pair has Syntegris mapping definition
    mapping_defn = get_mapping_definition(op, ver, src, tgt)
    canon_op = get_operation(op, ver)

    syntegris_evidence: dict[str, Any] = {
        "canonicalDefined": canon_op is not None,
        "mappingReady": False,
        "releaseReady": False,
        "runtimeIntegrated": False,
    }

    # Not in Syntegris mapping engine
    if mapping_defn is None:
        if canon_op is not None:
            adoption_status = CANON_DEFINED
            next_action = {
                "code": "GENERATE_SCAFFOLD",
                "title": "Generate scaffold for vendor pair",
                "targetRoute": "/admin/canonical-mappings",
            }
            notes.append("Canonical operation exists; vendor-pair mapping not yet in Syntegris.")
        else:
            adoption_status = LEGACY_ONLY
            next_action = {
                "code": "ONBOARD_CANONICAL",
                "title": "Define canonical and onboard",
                "targetRoute": "/admin/canonical-mappings",
            }
            notes.append("Runtime/control-plane evidence exists; no Syntegris canonical/mapping artifacts.")
        return {
            "operationCode": op,
            "version": ver,
            "sourceVendor": src,
            "targetVendor": tgt,
            "adoptionStatus": adoption_status,
            "inventoryEvidence": inv_evidence,
            "syntegrisEvidence": syntegris_evidence,
            "nextAction": next_action,
            "notes": notes,
        }

    # In mapping engine - get readiness and release readiness
    readiness = get_mapping_readiness(op, ver, src, tgt)
    release_item = _derive_release_readiness_item(readiness)
    onboarding_action = get_mapping_next_action(readiness)

    has_defn = bool(readiness.get("mappingDefinition"))
    has_fixtures = bool(readiness.get("fixtures"))
    cert_pass = bool(readiness.get("certification"))
    runtime_ready = bool(readiness.get("runtimeReady"))
    ready_for_promotion = bool(release_item.get("readyForPromotion"))
    status = (readiness.get("status") or "").strip().upper()

    syntegris_evidence["mappingReady"] = has_defn and has_fixtures
    syntegris_evidence["releaseReady"] = ready_for_promotion
    syntegris_evidence["runtimeIntegrated"] = runtime_ready

    # Determine adoption status
    if _is_supported_slice(op, src, tgt) and ready_for_promotion:
        adoption_status = SYNTEGRIS_READY
        next_action = {
            "code": "READY",
            "title": "No action required",
            "targetRoute": "/admin/canonical-mapping-readiness",
        }
    elif ready_for_promotion:
        adoption_status = RELEASE_READY
        next_action = {
            "code": "READY",
            "title": "Ready for promotion",
            "targetRoute": "/admin/canonical-mapping-readiness",
        }
    elif has_defn and has_fixtures and cert_pass and status == "READY":
        adoption_status = CERTIFIED
        next_action = onboarding_action
    elif has_defn or has_fixtures:
        adoption_status = MAPPING_IN_PROGRESS
        next_action = onboarding_action
    elif status == "WARN":
        adoption_status = BLOCKED
        next_action = onboarding_action
        notes.append("Certification or readiness inconsistent.")
    else:
        adoption_status = MAPPING_IN_PROGRESS
        next_action = onboarding_action

    # Ensure targetRoute in nextAction
    if "targetRoute" not in next_action:
        next_action["targetRoute"] = _route_for_action(
            next_action.get("code", ""),
            next_action.get("prefill", {}),
        )

    return {
        "operationCode": op,
        "version": ver,
        "sourceVendor": src,
        "targetVendor": tgt,
        "adoptionStatus": adoption_status,
        "inventoryEvidence": inv_evidence,
        "syntegrisEvidence": syntegris_evidence,
        "nextAction": {
            "code": next_action.get("code", "INVESTIGATE"),
            "title": next_action.get("title", "Investigate"),
            "targetRoute": next_action.get("targetRoute", "/admin/canonical-mapping-readiness"),
        },
        "notes": notes,
    }


def list_syntegris_adoption(
    conn: Any,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """List adoption classification for all inventory items.

    Args:
        conn: DB connection.
        filters: operationCode, sourceVendor, targetVendor, adoptionStatus, nextAction.

    Returns:
        { items, summary, notes }
    """
    from schema.integration_inventory import list_integration_inventory

    inv_filters = dict(filters or {})
    for k in ("adoptionStatus", "nextAction"):
        inv_filters.pop(k, None)

    inv_result = list_integration_inventory(conn, inv_filters)
    inv_items = inv_result.get("items") or []

    items: list[dict[str, Any]] = []
    adoption_filter = (filters or {}).get("adoptionStatus") or (filters or {}).get("adoption_status")
    next_action_filter = (filters or {}).get("nextAction") or (filters or {}).get("next_action")

    for inv in inv_items:
        item = classify_syntegris_adoption(inv)
        if adoption_filter and (item.get("adoptionStatus") or "").strip().upper() != str(adoption_filter).strip().upper():
            continue
        if next_action_filter and (item.get("nextAction") or {}).get("code", "").upper() != str(next_action_filter).strip().upper():
            continue
        items.append(item)

    summary = summarize_syntegris_adoption(items)
    return {
        "items": items,
        "summary": summary,
        "notes": [ADOPTION_NOTE],
    }


def get_syntegris_adoption_item(
    conn: Any,
    operation_code: str,
    source_vendor: str,
    target_vendor: str,
    version: str | None = None,
) -> dict[str, Any] | None:
    """Get adoption item for a specific operation/vendor pair.

    Returns None if pair not in inventory.
    """
    from schema.integration_inventory import get_integration_inventory_item

    inv = get_integration_inventory_item(conn, operation_code, source_vendor, target_vendor, version)
    if inv is None:
        return None
    return classify_syntegris_adoption(inv)


def summarize_syntegris_adoption(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Build summary counts by adoption status."""
    counts: dict[str, int] = {
        LEGACY_ONLY: 0,
        CANON_DEFINED: 0,
        MAPPING_IN_PROGRESS: 0,
        CERTIFIED: 0,
        RELEASE_READY: 0,
        SYNTEGRIS_READY: 0,
        BLOCKED: 0,
    }
    for item in items:
        status = (item.get("adoptionStatus") or "").strip().upper()
        if status in counts:
            counts[status] += 1
        else:
            counts[BLOCKED] = counts.get(BLOCKED, 0) + 1
    return {
        "total": len(items),
        "legacyOnly": counts[LEGACY_ONLY],
        "canonDefined": counts[CANON_DEFINED],
        "mappingInProgress": counts[MAPPING_IN_PROGRESS],
        "certified": counts[CERTIFIED],
        "releaseReady": counts[RELEASE_READY],
        "syntegrisReady": counts[SYNTEGRIS_READY],
        "blocked": counts[BLOCKED],
    }
