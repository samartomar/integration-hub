"""Mapping promotion artifact - code-first review artifact. No persistence. No runtime mutation.

Takes a proposal package and generates code-first promotion artifacts for manual apply.
Deterministic mappings remain authoritative. No file writes. No runtime mutation.
"""

from __future__ import annotations

from typing import Any

from schema.canonical_registry import resolve_version

# Operation code -> file prefix (lowercase, no underscores for filename)
_OP_TO_PREFIX: dict[str, str] = {
    "GET_VERIFY_MEMBER_ELIGIBILITY": "eligibility",
    "GET_MEMBER_ACCUMULATORS": "member_accumulators",
}

REVIEW_CHECKLIST = [
    "Confirm proposed target file path is correct.",
    "Confirm direct field mappings are correct.",
    "Confirm required fields are not dropped.",
    "Run mapping preview/validate tests after applying changes.",
]

TEST_CHECKLIST = [
    "Run mapping engine unit tests.",
    "Run mapping endpoint tests.",
    "Run runtime preflight tests for mapped operation.",
]

PROMOTION_NOTES = [
    "Promotion artifact only. No mapping definition was changed.",
]


def _infer_target_definition_file(op_code: str, version: str, source: str, target: str) -> str:
    """Infer target mapping definition file path from operation/version/vendor pair."""
    prefix = _OP_TO_PREFIX.get(op_code.upper(), op_code.lower().replace("_", "_"))
    # 1.0 -> v1, 2.0 -> v2
    parts = (version or "1.0").strip().split(".")
    major = parts[0] if parts else "1"
    ver_suffix = f"v{major}"
    src_lower = (source or "").strip().lower()
    tgt_lower = (target or "").strip().lower()
    return f"apps/api/src/schema/canonical_mappings/{prefix}_{ver_suffix}_{src_lower}_{tgt_lower}.py"


def _build_recommended_changes(proposal: dict[str, Any]) -> dict[str, Any]:
    """Build recommendedChanges from comparison or aiSuggestion."""
    comparison = proposal.get("comparison")
    ai_suggestion = proposal.get("aiSuggestion")
    added: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []

    if comparison:
        unchanged = list(comparison.get("unchanged") or [])
        added = list(comparison.get("added") or [])
        changed = list(comparison.get("changed") or [])
    elif ai_suggestion:
        mappings = ai_suggestion.get("proposedFieldMappings") or []
        for m in mappings:
            if isinstance(m, dict):
                unchanged.append({"from": m.get("from", ""), "to": m.get("to", "")})

    return {"added": added, "changed": changed, "unchanged": unchanged}


def build_mapping_promotion_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    """Build promotion artifact from proposal package.

    Requires proposalPackage with operationCode, version, sourceVendor, targetVendor, direction.
    Generates target file path, recommended changes, checklists, Python snippet.
    No file writes. No runtime mutation.
    """
    if not isinstance(payload, dict):
        return {
            "valid": False,
            "promotionArtifact": None,
            "pythonSnippet": None,
            "markdown": None,
            "notes": ["Invalid payload: must be a JSON object."],
        }

    proposal = payload.get("proposalPackage") or payload.get("proposal_package")
    if not isinstance(proposal, dict):
        return {
            "valid": False,
            "promotionArtifact": None,
            "pythonSnippet": None,
            "markdown": None,
            "notes": ["proposalPackage is required."],
        }

    op_code = (proposal.get("operationCode") or proposal.get("operation_code") or "").strip().upper()
    source = (proposal.get("sourceVendor") or proposal.get("source_vendor") or "").strip()
    target = (proposal.get("targetVendor") or proposal.get("target_vendor") or "").strip()
    version_in = (proposal.get("version") or "").strip()
    direction = (proposal.get("direction") or "CANONICAL_TO_VENDOR").strip().upper()

    if not op_code or not source or not target:
        return {
            "valid": False,
            "promotionArtifact": None,
            "pythonSnippet": None,
            "markdown": None,
            "notes": ["proposalPackage must include operationCode, sourceVendor, targetVendor."],
        }

    resolved = resolve_version(op_code, version_in or None)
    if resolved is None:
        return {
            "valid": False,
            "promotionArtifact": None,
            "pythonSnippet": None,
            "markdown": None,
            "notes": [f"Operation {op_code} version not found."],
        }

    target_file = _infer_target_definition_file(op_code, resolved, source, target)
    recommended = _build_recommended_changes(proposal)
    notes = list(proposal.get("notes", []))
    notes.extend(PROMOTION_NOTES)

    artifact: dict[str, Any] = {
        "proposalId": proposal.get("proposalId", ""),
        "operationCode": op_code,
        "version": resolved,
        "sourceVendor": source,
        "targetVendor": target,
        "direction": direction,
        "targetDefinitionFile": target_file,
        "recommendedChanges": recommended,
        "reviewChecklist": REVIEW_CHECKLIST,
        "testChecklist": TEST_CHECKLIST,
        "notes": notes,
    }
    if proposal.get("deterministicBaseline"):
        artifact["deterministicBaseline"] = proposal["deterministicBaseline"]
    if proposal.get("aiSuggestion"):
        artifact["aiSuggestion"] = proposal["aiSuggestion"]
    if proposal.get("comparison"):
        artifact["comparison"] = proposal["comparison"]

    python_snippet = build_mapping_definition_snippet(artifact)
    markdown = build_mapping_promotion_markdown(artifact)

    return {
        "valid": True,
        "promotionArtifact": artifact,
        "pythonSnippet": python_snippet,
        "markdown": markdown,
        "notes": notes,
    }


def build_mapping_definition_snippet(artifact: dict[str, Any]) -> str:
    """Build Python mapping-definition snippet preview for manual apply."""
    if not isinstance(artifact, dict):
        return "# Invalid artifact"

    op_code = (artifact.get("operationCode") or "").strip().upper()
    direction = (artifact.get("direction") or "CANONICAL_TO_VENDOR").strip().upper()
    target_file = artifact.get("targetDefinitionFile", "canonical_mappings/unknown.py")

    # Determine var prefix from operation
    var_prefix = "ELIGIBILITY" if op_code == "GET_VERIFY_MEMBER_ELIGIBILITY" else "ACCUMULATORS"
    if op_code == "GET_MEMBER_ACCUMULATORS":
        var_prefix = "ACCUMULATORS"

    dict_name = f"{var_prefix}_CANONICAL_TO_VENDOR" if direction == "CANONICAL_TO_VENDOR" else f"{var_prefix}_VENDOR_TO_CANONICAL"

    lines: list[str] = []
    lines.append(f"# Suggested mapping for {op_code} {direction}")
    lines.append(f"# Target file: {target_file}")
    lines.append("")
    lines.append(f"{dict_name}: dict[str, str | object] = {{")

    recommended = artifact.get("recommendedChanges") or {}
    added = recommended.get("added") or []
    unchanged = recommended.get("unchanged") or []
    changed = recommended.get("changed") or []

    # Build mapping entries: to_key -> $.from_key
    entries: list[tuple[str, str]] = []
    for item in unchanged:
        if isinstance(item, dict):
            to_k = item.get("to") or item.get("from")
            from_k = item.get("from") or item.get("to")
            if to_k and from_k:
                entries.append((str(to_k), f"$.{from_k}" if not str(from_k).startswith("$.") else from_k))
    for item in added:
        if isinstance(item, dict):
            to_k = item.get("to") or item.get("from")
            from_k = item.get("from") or item.get("to")
            if to_k and from_k:
                entries.append((str(to_k), f"$.{from_k}" if not str(from_k).startswith("$.") else from_k))
    for item in changed:
        if isinstance(item, dict) and "suggestedFrom" in item:
            to_k = item.get("to")
            sugg = item.get("suggestedFrom")
            if to_k and sugg:
                entries.append((str(to_k), f"$.{sugg}" if not str(sugg).startswith("$.") else sugg))

    # Fallback: use aiSuggestion proposedFieldMappings
    if not entries:
        ai_sugg = artifact.get("aiSuggestion")
        if ai_sugg:
            for m in ai_sugg.get("proposedFieldMappings") or []:
                if isinstance(m, dict):
                    to_k = m.get("to")
                    from_k = m.get("from")
                    if to_k and from_k:
                        entries.append((str(to_k), f"$.{from_k}" if not str(from_k).startswith("$.") else from_k))

    for to_key, from_val in entries:
        lines.append(f'    "{to_key}": "{from_val}",')
    if not entries:
        lines.append('    # Add field mappings here, e.g. "outKey": "$.inKey",')

    lines.append("}")
    return "\n".join(lines)


def build_mapping_promotion_markdown(artifact: dict[str, Any]) -> str:
    """Build markdown artifact for review/apply."""
    if not isinstance(artifact, dict):
        return "# Invalid Promotion Artifact\n\nArtifact object is invalid."

    lines: list[str] = []
    lines.append("# Mapping Promotion Artifact")
    lines.append("")
    lines.append(f"**Proposal ID:** `{artifact.get('proposalId', 'N/A')}`")
    lines.append("")
    lines.append("## Context")
    lines.append("")
    lines.append(f"- **Operation:** {artifact.get('operationCode', 'N/A')} v{artifact.get('version', 'N/A')}")
    lines.append(f"- **Source Vendor:** {artifact.get('sourceVendor', 'N/A')}")
    lines.append(f"- **Target Vendor:** {artifact.get('targetVendor', 'N/A')}")
    lines.append(f"- **Direction:** {artifact.get('direction', 'N/A')}")
    lines.append("")
    lines.append("## Target Definition File")
    lines.append("")
    lines.append(f"```")
    lines.append(artifact.get("targetDefinitionFile", "N/A"))
    lines.append("```")
    lines.append("")

    recommended = artifact.get("recommendedChanges") or {}
    u = recommended.get("unchanged") or []
    a = recommended.get("added") or []
    c = recommended.get("changed") or []
    lines.append("## Recommended Changes")
    lines.append("")
    lines.append(f"- **Unchanged:** {len(u)}")
    lines.append(f"- **Added:** {len(a)}")
    lines.append(f"- **Changed:** {len(c)}")
    lines.append("")

    lines.append("## Review Checklist")
    lines.append("")
    for item in artifact.get("reviewChecklist", []):
        lines.append(f"- [ ] {item}")
    lines.append("")
    lines.append("## Test Checklist")
    lines.append("")
    for item in artifact.get("testChecklist", []):
        lines.append(f"- [ ] {item}")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    for n in artifact.get("notes", []):
        lines.append(f"- {n}")
    lines.append("")
    lines.append("---")
    lines.append("*Promotion artifact only. No mapping definition was changed.*")
    return "\n".join(lines)
