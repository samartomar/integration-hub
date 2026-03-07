"""Mapping release readiness - deterministic release confidence reporting.

Derives release readiness from existing readiness/certification/runtime signals.
No persistence. No runtime mutation. Read-only. Admin-only.
"""

from __future__ import annotations

import uuid
from typing import Any

from schema.mapping_readiness import get_mapping_readiness, list_mapping_readiness

RELEASE_NOTE = "Release readiness is deterministic and read-only."
NO_RUNTIME_CHANGE_NOTE = "No runtime mapping was changed."

RELEASE_CHECKLIST = [
    "Review mapping definition changes.",
    "Review certification results.",
    "Review runtime preflight behavior.",
    "Complete manual code review and commit.",
]


def _derive_release_readiness_item(readiness_item: dict[str, Any]) -> dict[str, Any]:
    """Derive release readiness from a single readiness item."""
    if not isinstance(readiness_item, dict):
        return {
            "operationCode": "",
            "version": "1.0",
            "sourceVendor": "",
            "targetVendor": "",
            "readyForPromotion": False,
            "status": "MISSING",
            "blockers": ["Invalid readiness item."],
            "evidence": {
                "mappingDefinition": False,
                "fixtures": False,
                "certification": False,
                "runtimeReady": False,
            },
            "releaseChecklist": RELEASE_CHECKLIST,
            "notes": [RELEASE_NOTE, NO_RUNTIME_CHANGE_NOTE],
        }

    has_defn = bool(readiness_item.get("mappingDefinition"))
    has_fixtures = bool(readiness_item.get("fixtures"))
    has_cert = bool(readiness_item.get("certification"))
    runtime_ready = bool(readiness_item.get("runtimeReady"))
    status = (readiness_item.get("status") or "").strip().upper()

    blockers: list[str] = []
    if not has_defn:
        blockers.append("No mapping definition.")
    if not has_fixtures:
        blockers.append("No fixtures.")
    if has_defn and has_fixtures and not has_cert:
        blockers.append("Certification not passing.")
    if not runtime_ready:
        blockers.append("Runtime preflight not ready.")

    ready_for_promotion = (
        status == "READY"
        and has_defn
        and has_fixtures
        and has_cert
        and runtime_ready
        and len(blockers) == 0
    )

    return {
        "operationCode": readiness_item.get("operationCode", ""),
        "version": readiness_item.get("version", "1.0"),
        "sourceVendor": readiness_item.get("sourceVendor", ""),
        "targetVendor": readiness_item.get("targetVendor", ""),
        "readyForPromotion": ready_for_promotion,
        "status": status or "MISSING",
        "blockers": blockers,
        "evidence": {
            "mappingDefinition": has_defn,
            "fixtures": has_fixtures,
            "certification": has_cert,
            "runtimeReady": runtime_ready,
        },
        "releaseChecklist": list(RELEASE_CHECKLIST),
        "notes": [RELEASE_NOTE, NO_RUNTIME_CHANGE_NOTE],
    }


def list_mapping_release_readiness(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """List release readiness for all known pairs, optionally filtered.

    Filters: operationCode, sourceVendor, targetVendor, status, readyForPromotion
    """
    filters = filters or {}
    ready_filter = filters.get("readyForPromotion") or filters.get("ready_for_promotion")
    readiness_filters = {k: v for k, v in filters.items() if k not in ("readyForPromotion", "ready_for_promotion")}

    readiness_result = list_mapping_readiness(readiness_filters)
    items_raw = readiness_result.get("items") or []
    summary_raw = readiness_result.get("summary") or {}

    items: list[dict[str, Any]] = []
    for r in items_raw:
        item = _derive_release_readiness_item(r)
        if ready_filter is not None:
            want = ready_filter in (True, "true", "True", "1", "yes")
            if item.get("readyForPromotion") != want:
                continue
        items.append(item)

    summary = summarize_mapping_release_readiness(items)
    return {
        "items": items,
        "summary": summary,
        "notes": [RELEASE_NOTE, NO_RUNTIME_CHANGE_NOTE],
    }


def summarize_mapping_release_readiness(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Build summary counts from release readiness items."""
    ready_count = sum(1 for i in items if i.get("readyForPromotion"))
    return {
        "total": len(items),
        "readyForPromotion": ready_count,
        "notReady": len(items) - ready_count,
    }


def build_mapping_release_readiness_report(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate detailed release readiness report for a specific operation/vendor pair.

    Payload: operationCode, version (optional), sourceVendor, targetVendor
    Returns: { valid, report, markdown }
    """
    if not isinstance(payload, dict):
        return {
            "valid": False,
            "report": None,
            "markdown": "",
            "notes": ["Invalid payload."],
        }

    op = (payload.get("operationCode") or "").strip().upper()
    ver = (payload.get("version") or "1.0").strip()
    src = (payload.get("sourceVendor") or "").strip().upper()
    tgt = (payload.get("targetVendor") or "").strip().upper()

    if not op or not src or not tgt:
        return {
            "valid": False,
            "report": None,
            "markdown": "",
            "notes": ["operationCode, sourceVendor, and targetVendor are required."],
        }

    readiness = get_mapping_readiness(op, ver, src, tgt)
    item = _derive_release_readiness_item(readiness)
    ready = item.get("readyForPromotion", False)
    blockers = item.get("blockers") or []
    evidence = item.get("evidence") or {}
    checklist = item.get("releaseChecklist") or []

    recommended_next = (
        "Manual code review and promotion."
        if ready
        else (
            "Address blockers before promotion."
            if blockers
            else "Complete mapping definition, fixtures, and certification."
        )
    )

    report = {
        "reportId": str(uuid.uuid4()),
        "operationCode": op,
        "version": ver,
        "sourceVendor": src,
        "targetVendor": tgt,
        "status": item.get("status", "MISSING"),
        "readyForPromotion": ready,
        "blockers": blockers,
        "evidence": evidence,
        "releaseChecklist": checklist,
        "recommendedNextStep": recommended_next,
        "notes": ["Release report only. No code or runtime state was changed."],
    }

    markdown = _build_report_markdown(report)
    return {
        "valid": True,
        "report": report,
        "markdown": markdown,
        "notes": report["notes"],
    }


def build_mapping_release_readiness_markdown(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate markdown version of the release readiness report."""
    result = build_mapping_release_readiness_report(payload)
    if not result.get("valid"):
        return {
            "valid": False,
            "markdown": "",
            "notes": result.get("notes", ["Invalid request."]),
        }
    return {
        "valid": True,
        "markdown": result.get("markdown", ""),
        "reportId": (result.get("report") or {}).get("reportId"),
        "notes": result.get("notes", []),
    }


def _build_report_markdown(report: dict[str, Any]) -> str:
    """Build markdown representation of the report."""
    lines: list[str] = []
    lines.append("# Mapping Release Readiness Report")
    lines.append("")
    lines.append(f"**Operation:** {report.get('operationCode', '')} v{report.get('version', '1.0')}")
    lines.append(f"**Vendor Pair:** {report.get('sourceVendor', '')} → {report.get('targetVendor', '')}")
    lines.append(f"**Status:** {report.get('status', '')}")
    lines.append(f"**Ready for Promotion:** {'Yes' if report.get('readyForPromotion') else 'No'}")
    lines.append("")

    blockers = report.get("blockers") or []
    if blockers:
        lines.append("## Blockers")
        for b in blockers:
            lines.append(f"- {b}")
        lines.append("")

    evidence = report.get("evidence") or {}
    lines.append("## Evidence")
    lines.append(f"- Mapping definition: {'✓' if evidence.get('mappingDefinition') else '✗'}")
    lines.append(f"- Fixtures: {'✓' if evidence.get('fixtures') else '✗'}")
    lines.append(f"- Certification: {'✓' if evidence.get('certification') else '✗'}")
    lines.append(f"- Runtime ready: {'✓' if evidence.get('runtimeReady') else '✗'}")
    lines.append("")

    checklist = report.get("releaseChecklist") or []
    lines.append("## Release Checklist")
    for c in checklist:
        lines.append(f"- [ ] {c}")
    lines.append("")

    lines.append(f"**Recommended next step:** {report.get('recommendedNextStep', '')}")
    lines.append("")
    for n in report.get("notes") or []:
        lines.append(f"*{n}*")
    return "\n".join(lines)
