"""Tests for mapping promotion artifact service."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "apps" / "api" / "src"))

from schema.mapping_promotion_artifact import (
    build_mapping_promotion_artifact,
    build_mapping_definition_snippet,
    build_mapping_promotion_markdown,
)


def _minimal_proposal_package() -> dict:
    return {
        "proposalId": "test-proposal-123",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
    }


def test_proposal_package_converts_to_promotion_artifact() -> None:
    """Proposal package converts into promotion artifact correctly."""
    payload = {"proposalPackage": _minimal_proposal_package()}
    result = build_mapping_promotion_artifact(payload)
    assert result["valid"] is True
    artifact = result["promotionArtifact"]
    assert artifact is not None
    assert artifact["proposalId"] == "test-proposal-123"
    assert artifact["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert artifact["version"] == "1.0"
    assert artifact["sourceVendor"] == "LH001"
    assert artifact["targetVendor"] == "LH002"
    assert artifact["direction"] == "CANONICAL_TO_VENDOR"
    assert "targetDefinitionFile" in artifact
    assert "recommendedChanges" in artifact
    assert "reviewChecklist" in artifact
    assert "testChecklist" in artifact
    assert "notes" in artifact


def test_target_definition_file_inferred_correctly() -> None:
    """Target definition file path is inferred correctly."""
    payload = {"proposalPackage": _minimal_proposal_package()}
    result = build_mapping_promotion_artifact(payload)
    assert result["valid"] is True
    artifact = result["promotionArtifact"]
    assert artifact is not None
    path = artifact["targetDefinitionFile"]
    assert "eligibility" in path
    assert "v1" in path or "1" in path
    assert "lh001" in path.lower()
    assert "lh002" in path.lower()
    assert path.endswith(".py")
    assert path.startswith("apps/api/src/schema/canonical_mappings/")


def test_python_snippet_generated() -> None:
    """Python snippet is generated."""
    payload = {"proposalPackage": _minimal_proposal_package()}
    result = build_mapping_promotion_artifact(payload)
    assert result["valid"] is True
    snippet = result.get("pythonSnippet")
    assert snippet is not None
    assert "ELIGIBILITY" in snippet or "eligibility" in snippet.lower()
    assert "CANONICAL_TO_VENDOR" in snippet or "canonical_to_vendor" in snippet.lower()
    assert "Target file" in snippet or "target file" in snippet.lower()


def test_markdown_artifact_generated() -> None:
    """Markdown artifact is generated."""
    payload = {"proposalPackage": _minimal_proposal_package()}
    result = build_mapping_promotion_artifact(payload)
    assert result["valid"] is True
    md = result.get("markdown")
    assert md is not None
    assert "# Mapping Promotion Artifact" in md
    assert "## Target Definition File" in md
    assert "## Review Checklist" in md
    assert "## Test Checklist" in md
    assert "## Notes" in md
    assert "No mapping definition was changed" in md


def test_artifact_never_indicates_applied_state() -> None:
    """Artifact never indicates applied/runtime-changed state."""
    payload = {"proposalPackage": _minimal_proposal_package()}
    result = build_mapping_promotion_artifact(payload)
    assert result["valid"] is True
    artifact = result["promotionArtifact"]
    notes_str = " ".join(artifact.get("notes", []))
    assert "Promotion artifact only" in notes_str
    assert "No mapping definition was changed" in notes_str
    assert "applied" not in notes_str.lower() or "was changed" in notes_str


def test_version_alias_v1_normalizes() -> None:
    """Version alias v1 normalizes to 1.0 if needed."""
    pkg = _minimal_proposal_package()
    pkg["version"] = "v1"
    payload = {"proposalPackage": pkg}
    result = build_mapping_promotion_artifact(payload)
    assert result["valid"] is True
    artifact = result["promotionArtifact"]
    assert artifact is not None
    assert artifact["version"] == "1.0"


def test_recommended_changes_from_comparison() -> None:
    """Recommended changes populated from comparison."""
    pkg = _minimal_proposal_package()
    pkg["comparison"] = {
        "unchanged": [{"from": "a", "to": "b"}],
        "added": [{"from": "x", "to": "y"}],
        "changed": [{"from": "p", "to": "q", "suggestedFrom": "p2"}],
    }
    payload = {"proposalPackage": pkg}
    result = build_mapping_promotion_artifact(payload)
    assert result["valid"] is True
    rec = result["promotionArtifact"]["recommendedChanges"]
    assert len(rec["unchanged"]) == 1
    assert len(rec["added"]) == 1
    assert len(rec["changed"]) == 1


def test_invalid_payload_returns_valid_false() -> None:
    """Invalid payload returns valid=False."""
    result = build_mapping_promotion_artifact({})
    assert result["valid"] is False
    assert result["promotionArtifact"] is None
    assert "proposalpackage" in str(result.get("notes", [])[0]).lower()


def test_missing_proposal_package_returns_valid_false() -> None:
    """Missing proposalPackage returns valid=False."""
    result = build_mapping_promotion_artifact({"other": "data"})
    assert result["valid"] is False
    assert result["promotionArtifact"] is None


def test_missing_required_fields_returns_valid_false() -> None:
    """Missing operationCode/sourceVendor/targetVendor returns valid=False."""
    pkg = _minimal_proposal_package()
    pkg["operationCode"] = ""
    result = build_mapping_promotion_artifact({"proposalPackage": pkg})
    assert result["valid"] is False


def test_invalid_direction_accepted() -> None:
    """Invalid direction is accepted (service does not validate direction)."""
    pkg = _minimal_proposal_package()
    pkg["direction"] = "INVALID"
    result = build_mapping_promotion_artifact({"proposalPackage": pkg})
    assert result["valid"] is True


def test_build_mapping_definition_snippet_standalone() -> None:
    """build_mapping_definition_snippet works with artifact only."""
    artifact = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "direction": "CANONICAL_TO_VENDOR",
        "targetDefinitionFile": "apps/api/src/schema/canonical_mappings/eligibility_v1_lh001_lh002.py",
        "recommendedChanges": {
            "unchanged": [{"from": "memberIdWithPrefix", "to": "memberId"}],
            "added": [],
            "changed": [],
        },
    }
    snippet = build_mapping_definition_snippet(artifact)
    assert "ELIGIBILITY" in snippet
    assert "memberId" in snippet


def test_build_mapping_promotion_markdown_standalone() -> None:
    """build_mapping_promotion_markdown works with artifact only."""
    artifact = {
        "proposalId": "x",
        "operationCode": "OP",
        "version": "1.0",
        "sourceVendor": "S",
        "targetVendor": "T",
        "direction": "CANONICAL_TO_VENDOR",
        "targetDefinitionFile": "apps/api/src/schema/canonical_mappings/op_v1_s_t.py",
        "recommendedChanges": {"unchanged": [], "added": [], "changed": []},
        "reviewChecklist": ["Check 1"],
        "testChecklist": ["Test 1"],
        "notes": ["Note 1"],
    }
    md = build_mapping_promotion_markdown(artifact)
    assert "# Mapping Promotion Artifact" in md
    assert "op_v1_s_t.py" in md
    assert "Check 1" in md
    assert "Test 1" in md
