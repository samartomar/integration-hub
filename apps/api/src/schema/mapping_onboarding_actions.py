"""Mapping onboarding actions - deterministic next-action recommendations from readiness.

Derives recommended actions from existing readiness state. No persistence. No runtime mutation.
Read-only. Admin-only in this phase.
"""

from __future__ import annotations

from typing import Any

from schema.mapping_readiness import list_mapping_readiness

ONBOARDING_NOTE = "Recommended action is derived from deterministic readiness only."

# Action codes
GENERATE_SCAFFOLD = "GENERATE_SCAFFOLD"
COMPLETE_MAPPING_DEFINITION = "COMPLETE_MAPPING_DEFINITION"
ADD_FIXTURES = "ADD_FIXTURES"
RUN_CERTIFICATION = "RUN_CERTIFICATION"
REVIEW_PROMOTION_ARTIFACT = "REVIEW_PROMOTION_ARTIFACT"
READY = "READY"
INVESTIGATE_WARN = "INVESTIGATE_WARN"

TARGET_ROUTE = "/admin/canonical-mappings"


def _build_prefill(item: dict[str, Any]) -> dict[str, Any]:
    """Build prefill payload for CanonicalMappingPage."""
    return {
        "operationCode": item.get("operationCode", ""),
        "version": item.get("version", "1.0"),
        "sourceVendor": item.get("sourceVendor", ""),
        "targetVendor": item.get("targetVendor", ""),
    }


def get_mapping_next_action(readiness_item: dict[str, Any]) -> dict[str, Any]:
    """Derive next recommended action from a readiness item.

    Returns:
        {
            code, title, description, targetRoute, prefill
        }
    """
    if not isinstance(readiness_item, dict):
        return {
            "code": INVESTIGATE_WARN,
            "title": "Investigate",
            "description": "Invalid readiness item.",
            "targetRoute": TARGET_ROUTE,
            "prefill": {},
        }

    status = (readiness_item.get("status") or "").strip().upper()
    has_defn = bool(readiness_item.get("mappingDefinition"))
    has_fixtures = bool(readiness_item.get("fixtures"))
    cert_support = bool(readiness_item.get("certification"))
    prefill = _build_prefill(readiness_item)

    if status == "READY":
        return {
            "code": READY,
            "title": "Ready",
            "description": "Mapping is fully onboarded and certified.",
            "targetRoute": TARGET_ROUTE,
            "prefill": prefill,
        }

    if status == "MISSING" and not has_defn:
        return {
            "code": GENERATE_SCAFFOLD,
            "title": "Generate scaffold bundle",
            "description": "No mapping definition exists yet for this vendor pair.",
            "targetRoute": TARGET_ROUTE,
            "prefill": prefill,
        }

    if status == "WARN":
        if has_defn and has_fixtures and cert_support:
            return {
                "code": INVESTIGATE_WARN,
                "title": "Investigate certification",
                "description": "Certification failed. Review fixtures and mapping, then re-run certification.",
                "targetRoute": TARGET_ROUTE,
                "prefill": prefill,
            }
        return {
            "code": REVIEW_PROMOTION_ARTIFACT,
            "title": "Review promotion artifact",
            "description": "Artifacts exist but readiness is inconsistent. Review and fix.",
            "targetRoute": TARGET_ROUTE,
            "prefill": prefill,
        }

    if status == "IN_PROGRESS":
        if has_defn and not has_fixtures:
            return {
                "code": ADD_FIXTURES,
                "title": "Add fixtures",
                "description": "Mapping definition exists but no fixtures. Add fixture cases for certification.",
                "targetRoute": TARGET_ROUTE,
                "prefill": prefill,
            }
        if has_defn and has_fixtures:
            return {
                "code": RUN_CERTIFICATION,
                "title": "Run certification",
                "description": "Mapping and fixtures exist. Run certification to verify.",
                "targetRoute": TARGET_ROUTE,
                "prefill": prefill,
            }
        if not has_defn and has_fixtures:
            return {
                "code": COMPLETE_MAPPING_DEFINITION,
                "title": "Complete mapping definition",
                "description": "Fixtures exist but mapping definition is missing or incomplete.",
                "targetRoute": TARGET_ROUTE,
                "prefill": prefill,
            }
        return {
            "code": COMPLETE_MAPPING_DEFINITION,
            "title": "Complete mapping",
            "description": "Partial artifacts present. Complete mapping definition and add fixtures.",
            "targetRoute": TARGET_ROUTE,
            "prefill": prefill,
        }

    return {
        "code": INVESTIGATE_WARN,
        "title": "Investigate",
        "description": "Unknown readiness state.",
        "targetRoute": TARGET_ROUTE,
        "prefill": prefill,
    }


def build_onboarding_action_payload(readiness_item: dict[str, Any]) -> dict[str, Any]:
    """Build full onboarding action payload for a readiness item."""
    next_action = get_mapping_next_action(readiness_item)
    return {
        "operationCode": readiness_item.get("operationCode", ""),
        "version": readiness_item.get("version", "1.0"),
        "sourceVendor": readiness_item.get("sourceVendor", ""),
        "targetVendor": readiness_item.get("targetVendor", ""),
        "status": readiness_item.get("status", ""),
        "nextAction": next_action,
        "notes": [ONBOARDING_NOTE],
    }


def list_mapping_onboarding_actions(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """List onboarding actions for all known pairs, derived from readiness.

    Filters: operationCode, sourceVendor, targetVendor, status, nextAction
    """
    filters = filters or {}
    next_action_filter = (filters.get("nextAction") or filters.get("next_action") or "").strip().upper()

    readiness_result = list_mapping_readiness(filters)
    items_raw = readiness_result.get("items") or []
    summary = readiness_result.get("summary") or {}

    items: list[dict[str, Any]] = []
    for r in items_raw:
        payload = build_onboarding_action_payload(r)
        if next_action_filter and (payload.get("nextAction") or {}).get("code", "").upper() != next_action_filter:
            continue
        items.append(payload)

    return {
        "items": items,
        "summary": summary,
        "notes": [ONBOARDING_NOTE],
    }
