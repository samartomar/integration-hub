"""Tests for mapping proposal package service."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "apps" / "api" / "src"))

from schema.mapping_proposal_package import (
    build_mapping_proposal_package,
    build_mapping_proposal_json,
    build_mapping_proposal_markdown,
)


def test_baseline_only_package_builds_correctly() -> None:
    """Baseline-only package builds correctly."""
    payload = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
    }
    result = build_mapping_proposal_package(payload)
    assert result["valid"] is True
    pkg = result["proposalPackage"]
    assert pkg is not None
    assert pkg["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert pkg["version"] == "1.0"
    assert pkg["sourceVendor"] == "LH001"
    assert pkg["targetVendor"] == "LH002"
    assert pkg["direction"] == "CANONICAL_TO_VENDOR"
    assert pkg["deterministicBaseline"]["fieldMappings"] == 2
    assert "proposalId" in pkg
    assert "createdAt" in pkg
    assert "reviewChecklist" in pkg
    assert "promotionGuidance" in pkg
    assert "aiSuggestion" not in pkg
    assert "comparison" not in pkg
    assert "Proposal package only" in str(pkg.get("notes", []))


def test_baseline_plus_ai_suggestion_package_builds_correctly() -> None:
    """Baseline + AI suggestion package builds correctly."""
    payload = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
        "aiSuggestion": {
            "summary": "Suggested mappings",
            "proposedFieldMappings": [{"from": "memberIdWithPrefix", "to": "memberId"}],
            "proposedConstants": [],
            "warnings": [],
            "confidence": "medium",
        },
    }
    result = build_mapping_proposal_package(payload)
    assert result["valid"] is True
    pkg = result["proposalPackage"]
    assert pkg is not None
    assert pkg["aiSuggestion"] is not None
    assert pkg["aiSuggestion"]["summary"] == "Suggested mappings"
    assert len(pkg["aiSuggestion"]["proposedFieldMappings"]) == 1


def test_comparison_included_when_present() -> None:
    """Comparison is included when present."""
    payload = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
        "comparison": {"unchanged": [{"from": "a", "to": "b"}], "added": [], "changed": []},
    }
    result = build_mapping_proposal_package(payload)
    assert result["valid"] is True
    pkg = result["proposalPackage"]
    assert pkg is not None
    assert pkg["comparison"] is not None
    assert len(pkg["comparison"]["unchanged"]) == 1


def test_version_alias_v1_normalizes_to_1_0() -> None:
    """Version alias v1 normalizes to 1.0."""
    payload = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "v1",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 0, "constants": 0, "warnings": []},
    }
    result = build_mapping_proposal_package(payload)
    assert result["valid"] is True
    pkg = result["proposalPackage"]
    assert pkg is not None
    assert pkg["version"] == "1.0"


def test_package_never_indicates_applied_state() -> None:
    """Package never indicates applied/runtime-changed state."""
    payload = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
    }
    result = build_mapping_proposal_package(payload)
    pkg = result["proposalPackage"]
    assert pkg is not None
    notes_str = " ".join(pkg.get("notes", []))
    assert "Proposal package only" in notes_str
    assert "No runtime mapping was changed" in notes_str


def test_markdown_artifact_builds_with_expected_sections() -> None:
    """Markdown artifact builds with expected sections."""
    pkg = {
        "proposalId": "test-id",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "createdAt": "2025-03-06T12:00:00Z",
        "deterministicBaseline": {"fieldMappings": 2, "constants": 0, "warnings": []},
        "reviewChecklist": ["Check 1"],
        "promotionGuidance": ["Step 1"],
        "notes": ["Note 1"],
    }
    md = build_mapping_proposal_markdown(pkg)
    assert "# Mapping Proposal Package" in md
    assert "## Context" in md
    assert "## Deterministic Baseline" in md
    assert "## Review Checklist" in md
    assert "## Promotion Guidance" in md
    assert "## Notes" in md
    assert "GET_VERIFY_MEMBER_ELIGIBILITY" in md
    assert "LH001" in md
    assert "No runtime mapping was changed" in md


def test_markdown_includes_ai_suggestion_when_present() -> None:
    """Markdown includes AI suggestion section when present."""
    pkg = {
        "proposalId": "test-id",
        "operationCode": "OP",
        "version": "1.0",
        "sourceVendor": "S",
        "targetVendor": "T",
        "direction": "CANONICAL_TO_VENDOR",
        "createdAt": "2025-03-06",
        "deterministicBaseline": {"fieldMappings": 0, "constants": 0, "warnings": []},
        "aiSuggestion": {
            "summary": "AI summary",
            "proposedFieldMappings": [{"from": "a", "to": "b"}],
            "confidence": "high",
        },
        "reviewChecklist": [],
        "promotionGuidance": [],
        "notes": [],
    }
    md = build_mapping_proposal_markdown(pkg)
    assert "## AI Suggestion" in md
    assert "Advisory Only" in md
    assert "AI summary" in md
    assert "`a` → `b`" in md


def test_invalid_payload_returns_valid_false() -> None:
    """Invalid payload returns valid=False."""
    result = build_mapping_proposal_package({})
    assert result["valid"] is False
    assert result["proposalPackage"] is None


def test_missing_required_fields_returns_valid_false() -> None:
    """Missing operationCode/sourceVendor/targetVendor returns valid=False."""
    result = build_mapping_proposal_package({
        "operationCode": "OP",
        "sourceVendor": "",
        "targetVendor": "T",
        "direction": "CANONICAL_TO_VENDOR",
        "deterministicBaseline": {},
    })
    assert result["valid"] is False


def test_build_mapping_proposal_json_returns_copy() -> None:
    """build_mapping_proposal_json returns normalized copy."""
    pkg = {"proposalId": "x", "operationCode": "OP"}
    out = build_mapping_proposal_json(pkg)
    assert out == pkg
    assert out is not pkg
