"""Tests for mapping certification service."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "apps" / "api" / "src"))

from schema.mapping_certification import (
    list_mapping_fixtures_api,
    run_mapping_certification,
    summarize_mapping_certification,
)
from schema.mapping_fixtures import list_mapping_fixtures


def test_list_mapping_fixtures_returns_items() -> None:
    """list_mapping_fixtures returns fixture items."""
    fixtures = list_mapping_fixtures()
    assert len(fixtures) >= 4
    ids = {f.get("fixtureId") for f in fixtures}
    assert "eligibility-c2v-basic" in ids or "accumulators-c2v-basic" in ids


def test_list_mapping_fixtures_filtered_by_operation() -> None:
    """list_mapping_fixtures filters by operation_code."""
    fixtures = list_mapping_fixtures(operation_code="GET_VERIFY_MEMBER_ELIGIBILITY")
    assert len(fixtures) >= 2
    for f in fixtures:
        assert "eligibility" in (f.get("fixtureId") or "").lower()


def test_list_mapping_fixtures_api_returns_structure() -> None:
    """list_mapping_fixtures_api returns fixtureSet, items, notes."""
    result = list_mapping_fixtures_api(
        operation_code="GET_VERIFY_MEMBER_ELIGIBILITY",
        version="1.0",
        source_vendor="LH001",
        target_vendor="LH002",
    )
    assert "fixtureSet" in result
    assert "items" in result
    assert "notes" in result
    assert len(result["items"]) >= 2


def test_eligibility_canonical_to_vendor_certification_passes() -> None:
    """Eligibility CANONICAL_TO_VENDOR certification passes."""
    payload = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
    }
    result = run_mapping_certification(payload)
    assert result["valid"] is True
    assert result["summary"]["status"] == "PASS"
    assert result["summary"]["passed"] >= 1
    assert result["summary"]["failed"] == 0


def test_eligibility_vendor_to_canonical_certification_passes() -> None:
    """Eligibility VENDOR_TO_CANONICAL certification passes."""
    payload = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "VENDOR_TO_CANONICAL",
    }
    result = run_mapping_certification(payload)
    assert result["valid"] is True
    assert result["summary"]["status"] == "PASS"
    assert result["summary"]["passed"] >= 1
    assert result["summary"]["failed"] == 0


def test_accumulators_canonical_to_vendor_certification_passes() -> None:
    """Accumulators CANONICAL_TO_VENDOR certification passes."""
    payload = {
        "operationCode": "GET_MEMBER_ACCUMULATORS",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
    }
    result = run_mapping_certification(payload)
    assert result["valid"] is True
    assert result["summary"]["status"] == "PASS"
    assert result["summary"]["passed"] >= 1
    assert result["summary"]["failed"] == 0


def test_accumulators_vendor_to_canonical_certification_passes() -> None:
    """Accumulators VENDOR_TO_CANONICAL certification passes."""
    payload = {
        "operationCode": "GET_MEMBER_ACCUMULATORS",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "VENDOR_TO_CANONICAL",
    }
    result = run_mapping_certification(payload)
    assert result["valid"] is True
    assert result["summary"]["status"] == "PASS"
    assert result["summary"]["passed"] >= 1
    assert result["summary"]["failed"] == 0


def test_missing_mapping_definition_fails_clearly() -> None:
    """Certification for unknown vendor pair fails with clear message."""
    payload = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "UNKNOWN",
        "targetVendor": "UNKNOWN",
        "direction": "CANONICAL_TO_VENDOR",
    }
    result = run_mapping_certification(payload)
    assert result["valid"] is False
    assert "No fixtures" in str(result.get("notes", []))


def test_candidate_mapping_returns_warn() -> None:
    """Supplying candidateMapping returns WARN and not-supported message."""
    payload = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "candidateMapping": {"canonicalToVendor": {}},
    }
    result = run_mapping_certification(payload)
    assert result["summary"]["status"] == "WARN"
    assert any("candidatemapping" in str(n).lower() for n in result.get("notes", []))


def test_summarize_mapping_certification() -> None:
    """summarize_mapping_certification builds correct status."""
    assert summarize_mapping_certification({"passed": 3, "failed": 0, "warnings": 0})["status"] == "PASS"
    assert summarize_mapping_certification({"passed": 2, "failed": 1, "warnings": 0})["status"] == "FAIL"
    assert summarize_mapping_certification({"passed": 3, "failed": 0, "warnings": 1})["status"] == "WARN"


def test_certification_never_executes_runtime() -> None:
    """Certification notes explicitly state no runtime execution."""
    payload = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
    }
    result = run_mapping_certification(payload)
    notes_str = " ".join(result.get("notes", []))
    assert "No runtime execution" in notes_str or "runtime" in notes_str.lower()


def test_invalid_payload_returns_valid_false() -> None:
    """Invalid payload returns valid=False."""
    result = run_mapping_certification({})
    assert result["valid"] is False
    assert result["summary"]["status"] == "FAIL"


def test_missing_required_fields_returns_valid_false() -> None:
    """Missing operationCode/sourceVendor/targetVendor returns valid=False."""
    result = run_mapping_certification({
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "sourceVendor": "",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
    })
    assert result["valid"] is False
