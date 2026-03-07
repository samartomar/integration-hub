"""Mapping release bundle - deterministic batch release planning artifact.

Groups multiple READY mappings into a single review artifact for release coordination.
Derived from existing readiness/release-readiness. No persistence. No runtime mutation.
Read-only. Admin-only.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from schema.mapping_release_readiness import (
    _derive_release_readiness_item,
    list_mapping_release_readiness,
)
from schema.mapping_readiness import get_mapping_readiness

BUNDLE_NOTE = "Release bundle only. No mappings were changed or applied."

# Operation code -> file prefix (matches mapping_promotion_artifact)
_OP_TO_PREFIX: dict[str, str] = {
    "GET_VERIFY_MEMBER_ELIGIBILITY": "eligibility",
    "GET_MEMBER_ACCUMULATORS": "member_accumulators",
}

BUNDLE_VERIFICATION_CHECKLIST = [
    "Review all included mapping definition changes.",
    "Confirm certification passed for each mapping.",
    "Confirm runtime preflight remains healthy for included operations.",
    "Complete manual code review and release commit.",
]


def _infer_target_definition_file(op_code: str, version: str, source: str, target: str) -> str:
    """Infer target mapping definition file path from operation/version/vendor pair."""
    prefix = _OP_TO_PREFIX.get(op_code.upper(), op_code.lower().replace("_", "_"))
    parts = (version or "1.0").strip().split(".")
    major = parts[0] if parts else "1"
    ver_suffix = f"v{major}"
    src_lower = (source or "").strip().lower()
    tgt_lower = (target or "").strip().lower()
    return f"apps/api/src/schema/canonical_mappings/{prefix}_{ver_suffix}_{src_lower}_{tgt_lower}.py"


def list_release_bundle_candidates(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """List candidate mappings for bundle creation.

    Uses release readiness. Filters: operationCode, sourceVendor, targetVendor,
    readyForPromotion, status.
    """
    result = list_mapping_release_readiness(filters)
    return {
        "items": result.get("items", []),
        "summary": result.get("summary", {}),
        "notes": [BUNDLE_NOTE],
    }


def build_mapping_release_bundle(payload: dict[str, Any]) -> dict[str, Any]:
    """Build deterministic release bundle from selected items.

    Payload: bundleName (optional), items: [{ operationCode, version?, sourceVendor, targetVendor }]
    Returns: { valid, bundle, markdown }
    """
    if not isinstance(payload, dict):
        return {
            "valid": False,
            "bundle": None,
            "markdown": "",
            "notes": ["Invalid payload."],
        }

    items_raw = payload.get("items")
    if not isinstance(items_raw, list) or len(items_raw) == 0:
        return {
            "valid": False,
            "bundle": None,
            "markdown": "",
            "notes": ["items array with at least one entry is required."],
        }

    bundle_name = (payload.get("bundleName") or "").strip() or f"Release Bundle {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')}"
    bundle_id = str(uuid.uuid4())
    created_at = datetime.now(UTC).isoformat()

    bundle_items: list[dict[str, Any]] = []
    impacted_files: list[str] = []
    ready_count = 0
    blocked_count = 0

    for raw in items_raw:
        if not isinstance(raw, dict):
            continue
        op = (raw.get("operationCode") or "").strip().upper()
        ver = (raw.get("version") or "1.0").strip()
        src = (raw.get("sourceVendor") or "").strip().upper()
        tgt = (raw.get("targetVendor") or "").strip().upper()
        if not op or not src or not tgt:
            continue

        readiness = get_mapping_readiness(op, ver, src, tgt)
        item = _derive_release_readiness_item(readiness)
        ready = item.get("readyForPromotion", False)
        if ready:
            ready_count += 1
        else:
            blocked_count += 1

        target_file = _infer_target_definition_file(op, ver, src, tgt)
        if target_file and target_file not in impacted_files:
            impacted_files.append(target_file)

        bundle_items.append({
            "operationCode": op,
            "version": ver,
            "sourceVendor": src,
            "targetVendor": tgt,
            "readyForPromotion": ready,
            "status": item.get("status", "MISSING"),
            "targetDefinitionFile": target_file,
            "evidence": item.get("evidence", {}),
            "blockers": item.get("blockers", []),
        })

    if not bundle_items:
        return {
            "valid": False,
            "bundle": None,
            "markdown": "",
            "notes": ["No valid items. Each item needs operationCode, sourceVendor, targetVendor."],
        }

    bundle_status = "READY" if blocked_count == 0 else "BLOCKED"
    summary = {
        "included": len(bundle_items),
        "ready": ready_count,
        "blocked": blocked_count,
        "status": bundle_status,
    }

    bundle = {
        "bundleId": bundle_id,
        "bundleName": bundle_name,
        "createdAt": created_at,
        "summary": summary,
        "items": bundle_items,
        "impactedFiles": sorted(impacted_files),
        "verificationChecklist": list(BUNDLE_VERIFICATION_CHECKLIST),
        "notes": [BUNDLE_NOTE],
    }

    markdown = build_mapping_release_bundle_markdown(bundle)
    return {
        "valid": True,
        "bundle": bundle,
        "markdown": markdown,
        "notes": [BUNDLE_NOTE],
    }


def build_mapping_release_bundle_markdown(bundle: dict[str, Any]) -> str:
    """Generate markdown representation of the release bundle."""
    lines: list[str] = []
    lines.append(f"# {bundle.get('bundleName', 'Release Bundle')}")
    lines.append("")
    lines.append(f"**Bundle ID:** {bundle.get('bundleId', 'N/A')}")
    lines.append(f"**Created:** {bundle.get('createdAt', 'N/A')}")
    summary = bundle.get("summary") or {}
    lines.append(f"**Status:** {summary.get('status', 'N/A')} (included: {summary.get('included', 0)}, ready: {summary.get('ready', 0)}, blocked: {summary.get('blocked', 0)})")
    lines.append("")

    lines.append("## Included Mappings")
    for item in bundle.get("items") or []:
        ready = "✓" if item.get("readyForPromotion") else "✗"
        lines.append(f"- {item.get('operationCode', '')} v{item.get('version', '1.0')} {item.get('sourceVendor', '')} → {item.get('targetVendor', '')} {ready}")
        if item.get("blockers"):
            for b in item["blockers"]:
                lines.append(f"  - Blocker: {b}")
    lines.append("")

    impacted = bundle.get("impactedFiles") or []
    if impacted:
        lines.append("## Impacted Files")
        for f in impacted:
            lines.append(f"- `{f}`")
        lines.append("")

    lines.append("## Verification Checklist")
    for c in bundle.get("verificationChecklist") or []:
        lines.append(f"- [ ] {c}")
    lines.append("")

    for n in bundle.get("notes") or []:
        lines.append(f"*{n}*")
    return "\n".join(lines)


def summarize_mapping_release_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Extract summary from a bundle (convenience)."""
    return (bundle.get("summary") or {}).copy()
