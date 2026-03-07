"""Mapping scaffold generator - code-first onboarding artifact. No persistence. No runtime mutation.

Generates scaffold bundles for new operation/vendor-pair mappings.
Deterministic mappings remain authoritative. No file writes. No runtime mutation.
"""

from __future__ import annotations

from typing import Any

from schema.canonical_registry import resolve_version

# Operation code -> file prefix (lowercase)
_OP_TO_PREFIX: dict[str, str] = {
    "GET_VERIFY_MEMBER_ELIGIBILITY": "eligibility",
    "GET_MEMBER_ACCUMULATORS": "member_accumulators",
}

# Operation code -> variable prefix for mapping dict names
_OP_TO_VAR_PREFIX: dict[str, str] = {
    "GET_VERIFY_MEMBER_ELIGIBILITY": "ELIGIBILITY",
    "GET_MEMBER_ACCUMULATORS": "ACCUMULATORS",
}

SUPPORTED_OPERATIONS = frozenset(_OP_TO_PREFIX.keys())

SCAFFOLD_REVIEW_CHECKLIST = [
    "Confirm vendor pair naming is correct.",
    "Confirm canonical operation/version exists.",
    "Fill in field mappings for both directions.",
    "Add fixture cases before certification.",
]

SCAFFOLD_NOTES = [
    "Scaffold only. No mapping was created or applied.",
]


def _infer_paths(op_code: str, version: str, source: str, target: str) -> dict[str, str]:
    """Infer file paths from operation/version/vendor pair."""
    prefix = _OP_TO_PREFIX.get(op_code.upper(), op_code.lower().replace("_", "_"))
    parts = (version or "1.0").strip().split(".")
    major = parts[0] if parts else "1"
    ver_suffix = f"v{major}"
    src_lower = (source or "").strip().lower()
    tgt_lower = (target or "").strip().lower()
    base = f"{prefix}_{ver_suffix}_{src_lower}_{tgt_lower}"
    return {
        "mappingDefinitionFile": f"apps/api/src/schema/canonical_mappings/{base}.py",
        "fixtureFile": f"apps/api/src/schema/mapping_fixtures/{base}.py",
        "testFile": f"tests/schema/test_mapping_certification_{base}.py",
    }


def build_mapping_scaffold_bundle(payload: dict[str, Any]) -> dict[str, Any]:
    """Build scaffold bundle for new operation/vendor-pair mapping.

    Generates mapping definition stub, fixture stub, test stub, markdown.
    No file writes. No runtime mutation.
    """
    if not isinstance(payload, dict):
        return {
            "valid": False,
            "scaffoldBundle": None,
            "mappingDefinitionStub": None,
            "fixtureStub": None,
            "testStub": None,
            "markdown": None,
            "notes": ["Request body must be a JSON object."],
        }

    op_code = (payload.get("operationCode") or payload.get("operation_code") or "").strip().upper()
    version_in = (payload.get("version") or "").strip()
    source = (payload.get("sourceVendor") or payload.get("source_vendor") or "").strip()
    target = (payload.get("targetVendor") or payload.get("target_vendor") or "").strip()
    directions_raw = payload.get("directions") or payload.get("direction")
    if isinstance(directions_raw, str):
        directions = [d.strip().upper() for d in [directions_raw] if d.strip()]
    elif isinstance(directions_raw, list):
        directions = [str(d).strip().upper() for d in directions_raw if str(d).strip()]
    else:
        directions = ["CANONICAL_TO_VENDOR", "VENDOR_TO_CANONICAL"]

    if not op_code:
        return _scaffold_error("operationCode is required", op_code, version_in, source, target)
    if not source:
        return _scaffold_error("sourceVendor is required", op_code, version_in, source, target)
    if not target:
        return _scaffold_error("targetVendor is required", op_code, version_in, source, target)
    if op_code not in SUPPORTED_OPERATIONS:
        return _scaffold_error(
            f"Operation {op_code} is not supported. Supported: {', '.join(sorted(SUPPORTED_OPERATIONS))}",
            op_code, version_in, source, target,
        )

    resolved = resolve_version(op_code, version_in or None)
    if resolved is None:
        return _scaffold_error(
            f"Operation {op_code} version not found",
            op_code, version_in, source, target,
        )

    paths = _infer_paths(op_code, resolved, source, target)
    bundle: dict[str, Any] = {
        "operationCode": op_code,
        "version": resolved,
        "sourceVendor": source,
        "targetVendor": target,
        "mappingDefinitionFile": paths["mappingDefinitionFile"],
        "fixtureFile": paths["fixtureFile"],
        "testFile": paths["testFile"],
        "directions": directions,
        "reviewChecklist": list(SCAFFOLD_REVIEW_CHECKLIST),
        "notes": list(SCAFFOLD_NOTES),
    }

    mapping_stub = build_mapping_definition_stub(bundle)
    fixture_stub = build_mapping_fixture_stub(bundle)
    test_stub = build_mapping_test_stub(bundle)
    markdown = build_mapping_scaffold_markdown(bundle)

    return {
        "valid": True,
        "scaffoldBundle": bundle,
        "mappingDefinitionStub": mapping_stub,
        "fixtureStub": fixture_stub,
        "testStub": test_stub,
        "markdown": markdown,
        "notes": bundle["notes"],
    }


def build_mapping_definition_stub(bundle: dict[str, Any]) -> str:
    """Build Python mapping definition stub."""
    if not isinstance(bundle, dict):
        return "# Invalid bundle"
    op_code = (bundle.get("operationCode") or "").strip().upper()
    source = (bundle.get("sourceVendor") or "").strip()
    target = (bundle.get("targetVendor") or "").strip()
    var_prefix = _OP_TO_VAR_PREFIX.get(op_code, op_code.replace("_", "_").upper())
    directions = bundle.get("directions") or ["CANONICAL_TO_VENDOR", "VENDOR_TO_CANONICAL"]

    lines: list[str] = []
    lines.append(f'"""{op_code} mapping: {source} -> {target}.')
    lines.append("")
    lines.append("Canonical and vendor mapping. Fill in field mappings.")
    lines.append('"""')
    lines.append("")
    lines.append("from __future__ import annotations")
    lines.append("")
    if "CANONICAL_TO_VENDOR" in directions:
        lines.append("# CANONICAL_TO_VENDOR: input=canonical payload, output=vendor payload")
        lines.append(f"{var_prefix}_CANONICAL_TO_VENDOR: dict[str, str | object] = {{")
        lines.append('    # Add field mappings, e.g. "vendorKey": "$.canonicalKey",')
        lines.append("}")
        lines.append("")
    if "VENDOR_TO_CANONICAL" in directions:
        lines.append("# VENDOR_TO_CANONICAL: input=vendor payload, output=canonical payload")
        lines.append(f"{var_prefix}_VENDOR_TO_CANONICAL: dict[str, str | object] = {{")
        lines.append('    # Add field mappings, e.g. "canonicalKey": "$.vendorKey",')
        lines.append("}")
    return "\n".join(lines)


def build_mapping_fixture_stub(bundle: dict[str, Any]) -> str:
    """Build Python fixture stub."""
    if not isinstance(bundle, dict):
        return "# Invalid bundle"
    op_code = (bundle.get("operationCode") or "").strip().upper()
    source = (bundle.get("sourceVendor") or "").strip()
    target = (bundle.get("targetVendor") or "").strip()
    prefix = _OP_TO_PREFIX.get(op_code, "mapping").lower().replace("_", "_")
    directions = bundle.get("directions") or ["CANONICAL_TO_VENDOR", "VENDOR_TO_CANONICAL"]

    lines: list[str] = []
    lines.append(f'"""Fixture stub for {op_code} {source} -> {target}. Synthetic data only."""')
    lines.append("")
    lines.append("from __future__ import annotations")
    lines.append("")
    fix_var = f"{_OP_TO_VAR_PREFIX.get(op_code, prefix.upper())}_FIXTURES"
    lines.append(f"{fix_var}: list[dict] = [")
    if "CANONICAL_TO_VENDOR" in directions:
        lines.append("    {")
        lines.append('        "fixtureId": "c2v-basic",')
        lines.append('        "direction": "CANONICAL_TO_VENDOR",')
        lines.append('        "inputPayload": {},')
        lines.append('        "expectedOutput": {},')
        lines.append('        "notes": ["Add canonical-to-vendor fixture cases."],')
        lines.append("    },")
    if "VENDOR_TO_CANONICAL" in directions:
        lines.append("    {")
        lines.append('        "fixtureId": "v2c-basic",')
        lines.append('        "direction": "VENDOR_TO_CANONICAL",')
        lines.append('        "inputPayload": {},')
        lines.append('        "expectedOutput": {},')
        lines.append('        "notes": ["Add vendor-to-canonical fixture cases."],')
        lines.append("    },")
    lines.append("]")
    return "\n".join(lines)


def build_mapping_test_stub(bundle: dict[str, Any]) -> str:
    """Build Python test stub for certification."""
    if not isinstance(bundle, dict):
        return "# Invalid bundle"
    op_code = (bundle.get("operationCode") or "").strip().upper()
    source = (bundle.get("sourceVendor") or "").strip()
    target = (bundle.get("targetVendor") or "").strip()

    lines: list[str] = []
    lines.append('"""Tests for mapping certification - scaffold-generated."""')
    lines.append("")
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("import sys")
    lines.append("from pathlib import Path")
    lines.append("")
    lines.append("import pytest")
    lines.append("")
    lines.append('sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "apps" / "api" / "src"))')
    lines.append("")
    lines.append("from schema.mapping_certification import run_mapping_certification")
    lines.append("")
    lines.append("")
    lines.append(f"def test_{op_code.lower()}_{source.lower()}_{target.lower()}_canonical_to_vendor_passes() -> None:")
    lines.append(f'    """{op_code} CANONICAL_TO_VENDOR certification passes."""')
    lines.append("    payload = {")
    lines.append(f'        "operationCode": "{op_code}",')
    lines.append('        "version": "1.0",')
    lines.append(f'        "sourceVendor": "{source}",')
    lines.append(f'        "targetVendor": "{target}",')
    lines.append('        "direction": "CANONICAL_TO_VENDOR",')
    lines.append("    }")
    lines.append("    result = run_mapping_certification(payload)")
    lines.append('    assert result["valid"] is True')
    lines.append('    assert result["summary"]["status"] == "PASS"')
    lines.append("")
    lines.append("")
    lines.append(f"def test_{op_code.lower()}_{source.lower()}_{target.lower()}_vendor_to_canonical_passes() -> None:")
    lines.append(f'    """{op_code} VENDOR_TO_CANONICAL certification passes."""')
    lines.append("    payload = {")
    lines.append(f'        "operationCode": "{op_code}",')
    lines.append('        "version": "1.0",')
    lines.append(f'        "sourceVendor": "{source}",')
    lines.append(f'        "targetVendor": "{target}",')
    lines.append('        "direction": "VENDOR_TO_CANONICAL",')
    lines.append("    }")
    lines.append("    result = run_mapping_certification(payload)")
    lines.append('    assert result["valid"] is True')
    lines.append('    assert result["summary"]["status"] == "PASS"')
    return "\n".join(lines)


def build_mapping_scaffold_markdown(bundle: dict[str, Any]) -> str:
    """Build markdown onboarding artifact."""
    if not isinstance(bundle, dict):
        return "# Invalid Scaffold Bundle\n\nBundle object is invalid."
    lines: list[str] = []
    lines.append("# Mapping Scaffold Bundle")
    lines.append("")
    lines.append("## Context")
    lines.append("")
    lines.append(f"- **Operation:** {bundle.get('operationCode', 'N/A')} v{bundle.get('version', 'N/A')}")
    lines.append(f"- **Source Vendor:** {bundle.get('sourceVendor', 'N/A')}")
    lines.append(f"- **Target Vendor:** {bundle.get('targetVendor', 'N/A')}")
    lines.append("")
    lines.append("## Files to Create")
    lines.append("")
    lines.append(f"1. **Mapping definition:** `{bundle.get('mappingDefinitionFile', 'N/A')}`")
    lines.append(f"2. **Fixtures:** `{bundle.get('fixtureFile', 'N/A')}`")
    lines.append(f"3. **Tests:** `{bundle.get('testFile', 'N/A')}`")
    lines.append("")
    lines.append("## Review Checklist")
    lines.append("")
    for item in bundle.get("reviewChecklist", []):
        lines.append(f"- [ ] {item}")
    lines.append("")
    lines.append("## Onboarding Flow")
    lines.append("")
    lines.append("1. Create mapping definition file and fill field mappings")
    lines.append("2. Register mapping in canonical_mapping_engine (if not auto-discovered)")
    lines.append("3. Add fixture cases to mapping_fixtures")
    lines.append("4. Run certification")
    lines.append("5. Create promotion artifact if needed")
    lines.append("6. Manual code review and merge")
    lines.append("")
    lines.append("---")
    lines.append("*Scaffold only. No mapping was created or applied.*")
    return "\n".join(lines)


def _scaffold_error(
    message: str,
    op_code: str,
    version: str,
    source: str,
    target: str,
) -> dict[str, Any]:
    """Build scaffold error result."""
    return {
        "valid": False,
        "scaffoldBundle": None,
        "mappingDefinitionStub": None,
        "fixtureStub": None,
        "testStub": None,
        "markdown": None,
        "notes": [message, *SCAFFOLD_NOTES],
    }
