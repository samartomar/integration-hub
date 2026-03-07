"""Tests for mapping scaffold generator - deterministic onboarding artifact."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "apps" / "api" / "src"))

from schema.mapping_scaffold_generator import (
    SUPPORTED_OPERATIONS,
    build_mapping_definition_stub,
    build_mapping_fixture_stub,
    build_mapping_scaffold_bundle,
    build_mapping_scaffold_markdown,
    build_mapping_test_stub,
)


def _eligibility_payload() -> dict:
    return {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH003",
        "directions": ["CANONICAL_TO_VENDOR", "VENDOR_TO_CANONICAL"],
    }


def _accumulators_payload() -> dict:
    return {
        "operationCode": "GET_MEMBER_ACCUMULATORS",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "directions": ["CANONICAL_TO_VENDOR", "VENDOR_TO_CANONICAL"],
    }


@patch("schema.mapping_scaffold_generator.resolve_version")
def test_bundle_builds_correctly_for_eligibility_vendor_pair(mock_resolve: object) -> None:
    """Bundle builds correctly for eligibility vendor pair."""
    mock_resolve.return_value = "1.0"
    result = build_mapping_scaffold_bundle(_eligibility_payload())
    assert result["valid"] is True
    bundle = result["scaffoldBundle"]
    assert bundle is not None
    assert bundle["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert bundle["version"] == "1.0"
    assert bundle["sourceVendor"] == "LH001"
    assert bundle["targetVendor"] == "LH003"
    assert "eligibility_v1_lh001_lh003" in bundle["mappingDefinitionFile"]
    assert "eligibility_v1_lh001_lh003" in bundle["fixtureFile"]
    assert "test_mapping_certification_eligibility_v1_lh001_lh003" in bundle["testFile"]
    assert result["mappingDefinitionStub"]
    assert result["fixtureStub"]
    assert result["testStub"]
    assert result["markdown"]
    assert "Scaffold only" in str(result.get("notes", []))


@patch("schema.mapping_scaffold_generator.resolve_version")
def test_bundle_builds_correctly_for_accumulators_vendor_pair(mock_resolve: object) -> None:
    """Bundle builds correctly for accumulators vendor pair."""
    mock_resolve.return_value = "1.0"
    result = build_mapping_scaffold_bundle(_accumulators_payload())
    assert result["valid"] is True
    bundle = result["scaffoldBundle"]
    assert bundle is not None
    assert bundle["operationCode"] == "GET_MEMBER_ACCUMULATORS"
    assert bundle["sourceVendor"] == "LH001"
    assert bundle["targetVendor"] == "LH002"
    assert "member_accumulators_v1_lh001_lh002" in bundle["mappingDefinitionFile"]
    assert "member_accumulators_v1_lh001_lh002" in bundle["fixtureFile"]
    assert "test_mapping_certification_member_accumulators_v1_lh001_lh002" in bundle["testFile"]


@patch("schema.mapping_scaffold_generator.resolve_version")
def test_inferred_file_paths_are_correct(mock_resolve: object) -> None:
    """Inferred file paths follow expected conventions."""
    mock_resolve.return_value = "1.0"
    result = build_mapping_scaffold_bundle(_eligibility_payload())
    assert result["valid"] is True
    bundle = result["scaffoldBundle"]
    assert bundle["mappingDefinitionFile"] == (
        "apps/api/src/schema/canonical_mappings/eligibility_v1_lh001_lh003.py"
    )
    assert bundle["fixtureFile"] == (
        "apps/api/src/schema/mapping_fixtures/eligibility_v1_lh001_lh003.py"
    )
    assert bundle["testFile"] == (
        "tests/schema/test_mapping_certification_eligibility_v1_lh001_lh003.py"
    )


@patch("schema.mapping_scaffold_generator.resolve_version")
def test_mapping_definition_stub_is_generated(mock_resolve: object) -> None:
    """Mapping definition stub contains expected structure."""
    mock_resolve.return_value = "1.0"
    result = build_mapping_scaffold_bundle(_eligibility_payload())
    stub = result["mappingDefinitionStub"]
    assert "GET_VERIFY_MEMBER_ELIGIBILITY" in stub
    assert "LH001" in stub
    assert "LH003" in stub
    assert "ELIGIBILITY_CANONICAL_TO_VENDOR" in stub
    assert "ELIGIBILITY_VENDOR_TO_CANONICAL" in stub
    assert "from __future__ import annotations" in stub


@patch("schema.mapping_scaffold_generator.resolve_version")
def test_fixture_stub_is_generated(mock_resolve: object) -> None:
    """Fixture stub contains expected structure."""
    mock_resolve.return_value = "1.0"
    result = build_mapping_scaffold_bundle(_eligibility_payload())
    stub = result["fixtureStub"]
    assert "ELIGIBILITY_FIXTURES" in stub
    assert "CANONICAL_TO_VENDOR" in stub
    assert "VENDOR_TO_CANONICAL" in stub
    assert "fixtureId" in stub
    assert "inputPayload" in stub
    assert "expectedOutput" in stub


@patch("schema.mapping_scaffold_generator.resolve_version")
def test_test_stub_is_generated(mock_resolve: object) -> None:
    """Test stub contains expected structure."""
    mock_resolve.return_value = "1.0"
    result = build_mapping_scaffold_bundle(_eligibility_payload())
    stub = result["testStub"]
    assert "run_mapping_certification" in stub
    assert "test_" in stub
    assert "canonical_to_vendor" in stub
    assert "vendor_to_canonical" in stub
    assert "pytest" in stub


@patch("schema.mapping_scaffold_generator.resolve_version")
def test_markdown_artifact_is_generated(mock_resolve: object) -> None:
    """Markdown artifact contains expected sections."""
    mock_resolve.return_value = "1.0"
    result = build_mapping_scaffold_bundle(_eligibility_payload())
    md = result["markdown"]
    assert "# Mapping Scaffold Bundle" in md
    assert "GET_VERIFY_MEMBER_ELIGIBILITY" in md
    assert "LH001" in md
    assert "LH003" in md
    assert "Files to Create" in md
    assert "Review Checklist" in md
    assert "Onboarding Flow" in md
    assert "Scaffold only" in md


def test_invalid_operation_returns_clear_validation_error() -> None:
    """Invalid operation returns clear validation error."""
    payload = {
        "operationCode": "UNSUPPORTED_OP",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
    }
    result = build_mapping_scaffold_bundle(payload)
    assert result["valid"] is False
    assert result["scaffoldBundle"] is None
    assert "UNSUPPORTED_OP" in str(result.get("notes", []))
    assert "Supported" in str(result.get("notes", []))


def test_missing_operation_code_returns_error() -> None:
    """Missing operationCode returns validation error."""
    result = build_mapping_scaffold_bundle({
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
    })
    assert result["valid"] is False
    assert "operationcode" in str(result.get("notes", [])).lower()


def test_missing_source_vendor_returns_error() -> None:
    """Missing sourceVendor returns validation error."""
    result = build_mapping_scaffold_bundle({
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "targetVendor": "LH002",
    })
    assert result["valid"] is False
    assert "source" in str(result.get("notes", [])).lower()


def test_missing_target_vendor_returns_error() -> None:
    """Missing targetVendor returns validation error."""
    result = build_mapping_scaffold_bundle({
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "sourceVendor": "LH001",
    })
    assert result["valid"] is False
    assert "target" in str(result.get("notes", [])).lower()


@patch("schema.mapping_scaffold_generator.resolve_version")
def test_bundle_never_indicates_applied_state(mock_resolve: object) -> None:
    """Bundle never indicates applied or runtime-changed state."""
    mock_resolve.return_value = "1.0"
    result = build_mapping_scaffold_bundle(_eligibility_payload())
    notes = " ".join(result.get("notes", []))
    assert "Scaffold only" in notes
    assert "No mapping was created or applied" in notes
    assert "applied" not in notes.lower().replace("no mapping was created or applied", "").replace("scaffold only", "")


@patch("schema.mapping_scaffold_generator.resolve_version")
def test_non_dict_payload_returns_error(mock_resolve: object) -> None:
    """Non-dict payload returns validation error."""
    result = build_mapping_scaffold_bundle("not a dict")
    assert result["valid"] is False
    assert "JSON object" in str(result.get("notes", []))


@patch("schema.mapping_scaffold_generator.resolve_version")
def test_unknown_version_returns_error(mock_resolve: object) -> None:
    """Unknown version returns validation error."""
    mock_resolve.return_value = None
    result = build_mapping_scaffold_bundle(_eligibility_payload())
    assert result["valid"] is False
    assert "version" in str(result.get("notes", [])).lower()


def test_build_mapping_definition_stub_with_invalid_bundle() -> None:
    """build_mapping_definition_stub with invalid bundle returns fallback."""
    assert "# Invalid bundle" in build_mapping_definition_stub("not a dict")


def test_build_mapping_fixture_stub_with_invalid_bundle() -> None:
    """build_mapping_fixture_stub with invalid bundle returns fallback."""
    assert "# Invalid bundle" in build_mapping_fixture_stub("not a dict")


def test_build_mapping_test_stub_with_invalid_bundle() -> None:
    """build_mapping_test_stub with invalid bundle returns fallback."""
    assert "# Invalid bundle" in build_mapping_test_stub("not a dict")


def test_build_mapping_scaffold_markdown_with_invalid_bundle() -> None:
    """build_mapping_scaffold_markdown with invalid bundle returns fallback."""
    md = build_mapping_scaffold_markdown("not a dict")
    assert "Invalid" in md
    assert "Bundle" in md


def test_supported_operations_includes_eligibility_and_accumulators() -> None:
    """SUPPORTED_OPERATIONS includes expected operations."""
    assert "GET_VERIFY_MEMBER_ELIGIBILITY" in SUPPORTED_OPERATIONS
    assert "GET_MEMBER_ACCUMULATORS" in SUPPORTED_OPERATIONS
