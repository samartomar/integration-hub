"""Mapping proposal package - review-only artifact. No persistence. No runtime mutation.

Deterministic mappings remain authoritative. AI suggestions remain advisory.
Proposal packages are exportable/reviewable artifacts for human promotion.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from schema.canonical_registry import resolve_version

REVIEW_CHECKLIST = [
    "Confirm canonical source fields are correct.",
    "Confirm vendor target field paths are correct.",
    "Confirm no required field is dropped.",
    "Confirm suggestion is advisory only before promotion.",
]

PROMOTION_GUIDANCE = [
    "Review proposal manually.",
    "Update code-first mapping definition in canonical_mappings/.",
    "Run mapping preview/validate tests.",
    "Re-run runtime preflight before execute.",
]

PROPOSAL_NOTES = [
    "Proposal package only. No runtime mapping was changed.",
]


def build_mapping_proposal_package(payload: dict[str, Any]) -> dict[str, Any]:
    """Build a normalized proposal package from deterministic baseline + optional AI/comparison.

    Requires operationCode, sourceVendor, targetVendor, direction.
    Accepts deterministic baseline alone; includes AI suggestion and comparison only if present.
    Never claims proposal has been applied. No persistence.
    """
    if not isinstance(payload, dict):
        return {
            "valid": False,
            "proposalPackage": None,
            "markdown": None,
            "json": None,
            "notes": ["Invalid payload: must be a JSON object."],
        }

    op_code = (payload.get("operationCode") or payload.get("operation_code") or "").strip().upper()
    source = (payload.get("sourceVendor") or payload.get("source_vendor") or "").strip()
    target = (payload.get("targetVendor") or payload.get("target_vendor") or "").strip()
    version_in = (payload.get("version") or "").strip()
    direction = (payload.get("direction") or "CANONICAL_TO_VENDOR").strip().upper()

    if not op_code or not source or not target:
        return {
            "valid": False,
            "proposalPackage": None,
            "markdown": None,
            "json": None,
            "notes": ["Missing required fields: operationCode, sourceVendor, targetVendor."],
        }

    if direction not in ("CANONICAL_TO_VENDOR", "VENDOR_TO_CANONICAL"):
        return {
            "valid": False,
            "proposalPackage": None,
            "markdown": None,
            "json": None,
            "notes": ["Invalid direction. Must be CANONICAL_TO_VENDOR or VENDOR_TO_CANONICAL."],
        }

    resolved = resolve_version(op_code, version_in or None)
    if resolved is None:
        return {
            "valid": False,
            "proposalPackage": None,
            "markdown": None,
            "json": None,
            "notes": [f"Operation {op_code} version not found."],
        }

    deterministic_baseline = payload.get("deterministicBaseline") or payload.get("deterministic_baseline")
    if not isinstance(deterministic_baseline, dict):
        deterministic_baseline = {"fieldMappings": 0, "constants": 0, "warnings": ["No baseline provided."]}

    ai_suggestion = payload.get("aiSuggestion") or payload.get("ai_suggestion")
    if ai_suggestion is not None and not isinstance(ai_suggestion, dict):
        ai_suggestion = None

    comparison = payload.get("comparison") or payload.get("comparison_result")
    if comparison is not None and not isinstance(comparison, dict):
        comparison = None

    notes_in = payload.get("notes")
    if isinstance(notes_in, list):
        notes = list(notes_in)
    elif isinstance(notes_in, str):
        notes = [notes_in] if notes_in.strip() else []
    else:
        notes = []
    notes.extend(PROPOSAL_NOTES)

    proposal_id = str(uuid.uuid4())
    created_at = datetime.now(UTC).isoformat()

    proposal_package: dict[str, Any] = {
        "proposalId": proposal_id,
        "operationCode": op_code,
        "version": resolved,
        "sourceVendor": source,
        "targetVendor": target,
        "direction": direction,
        "createdAt": created_at,
        "deterministicBaseline": deterministic_baseline,
        "reviewChecklist": REVIEW_CHECKLIST,
        "promotionGuidance": PROMOTION_GUIDANCE,
        "notes": notes,
    }
    if ai_suggestion:
        proposal_package["aiSuggestion"] = ai_suggestion
    if comparison:
        proposal_package["comparison"] = comparison

    markdown = build_mapping_proposal_markdown(proposal_package)
    json_artifact = build_mapping_proposal_json(proposal_package)

    return {
        "valid": True,
        "proposalPackage": proposal_package,
        "markdown": markdown,
        "json": json_artifact,
        "notes": notes,
    }


def build_mapping_proposal_markdown(package_obj: dict[str, Any]) -> str:
    """Build markdown artifact for review/export."""
    if not isinstance(package_obj, dict):
        return "# Invalid Proposal Package\n\nPackage object is invalid."

    lines: list[str] = []
    lines.append("# Mapping Proposal Package")
    lines.append("")
    lines.append(f"**Proposal ID:** `{package_obj.get('proposalId', 'N/A')}`")
    lines.append(f"**Created:** {package_obj.get('createdAt', 'N/A')}")
    lines.append("")
    lines.append("## Context")
    lines.append("")
    lines.append(f"- **Operation:** {package_obj.get('operationCode', 'N/A')} v{package_obj.get('version', 'N/A')}")
    lines.append(f"- **Source Vendor:** {package_obj.get('sourceVendor', 'N/A')}")
    lines.append(f"- **Target Vendor:** {package_obj.get('targetVendor', 'N/A')}")
    lines.append(f"- **Direction:** {package_obj.get('direction', 'N/A')}")
    lines.append("")
    lines.append("## Deterministic Baseline")
    lines.append("")
    baseline = package_obj.get("deterministicBaseline") or {}
    lines.append(f"- Field mappings: {baseline.get('fieldMappings', 0)}")
    lines.append(f"- Constants: {baseline.get('constants', 0)}")
    for w in baseline.get("warnings", []):
        lines.append(f"- ⚠️ {w}")
    lines.append("")

    ai_suggestion = package_obj.get("aiSuggestion")
    if ai_suggestion:
        lines.append("## AI Suggestion (Advisory Only)")
        lines.append("")
        if ai_suggestion.get("summary"):
            lines.append(ai_suggestion["summary"])
            lines.append("")
        lines.append(f"**Confidence:** {ai_suggestion.get('confidence', 'N/A')}")
        lines.append("")
        mappings = ai_suggestion.get("proposedFieldMappings") or []
        if mappings:
            lines.append("**Proposed field mappings:**")
            lines.append("")
            for m in mappings:
                from_f = m.get("from", "")
                to_f = m.get("to", "")
                lines.append(f"- `{from_f}` → `{to_f}`")
            lines.append("")
        for w in ai_suggestion.get("warnings", []):
            lines.append(f"- ⚠️ {w}")
        lines.append("")

    comparison = package_obj.get("comparison")
    if comparison:
        lines.append("## Comparison")
        lines.append("")
        u = (comparison.get("unchanged") or [])
        a = (comparison.get("added") or [])
        c = (comparison.get("changed") or [])
        lines.append(f"- **Unchanged:** {len(u)}")
        lines.append(f"- **Added:** {len(a)}")
        lines.append(f"- **Changed:** {len(c)}")
        lines.append("")

    lines.append("## Review Checklist")
    lines.append("")
    for item in package_obj.get("reviewChecklist", []):
        lines.append(f"- [ ] {item}")
    lines.append("")
    lines.append("## Promotion Guidance")
    lines.append("")
    for item in package_obj.get("promotionGuidance", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    for n in package_obj.get("notes", []):
        lines.append(f"- {n}")
    lines.append("")
    lines.append("---")
    lines.append("*Proposal package only. No runtime mapping was changed.*")
    return "\n".join(lines)


def build_mapping_proposal_json(package_obj: dict[str, Any]) -> dict[str, Any]:
    """Build normalized JSON artifact (copy of package, no extra nesting)."""
    if not isinstance(package_obj, dict):
        return {"error": "Invalid package object"}
    return json.loads(json.dumps(package_obj, default=str))
