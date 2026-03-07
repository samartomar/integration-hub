"""Tests for mapping release readiness service."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from schema.mapping_release_readiness import (
    build_mapping_release_readiness_markdown,
    build_mapping_release_readiness_report,
    list_mapping_release_readiness,
    summarize_mapping_release_readiness,
)


def test_ready_lh001_lh002_returns_ready_for_promotion() -> None:
    """Current LH001->LH002 READY mappings return readyForPromotion=True."""
    result = list_mapping_release_readiness()
    assert "items" in result
    assert "summary" in result
    ready_items = [i for i in result["items"] if i.get("readyForPromotion")]
    assert len(ready_items) >= 2
    ops = {i["operationCode"] for i in ready_items}
    assert "GET_VERIFY_MEMBER_ELIGIBILITY" in ops
    assert "GET_MEMBER_ACCUMULATORS" in ops
    for item in ready_items:
        assert item["status"] == "READY"
        assert item["blockers"] == []
        assert item["evidence"]["mappingDefinition"] is True
        assert item["evidence"]["fixtures"] is True
        assert item["evidence"]["certification"] is True
        assert item["evidence"]["runtimeReady"] is True


@patch("schema.mapping_release_readiness.list_mapping_readiness")
def test_missing_mapping_returns_not_ready_with_blockers(mock_readiness: object) -> None:
    """Missing mapping returns readyForPromotion=False with blockers."""
    mock_readiness.return_value = {
        "items": [
            {
                "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
                "version": "1.0",
                "sourceVendor": "LH999",
                "targetVendor": "LH998",
                "mappingDefinition": False,
                "fixtures": False,
                "certification": False,
                "runtimeReady": False,
                "status": "MISSING",
            },
        ],
        "summary": {"total": 1, "ready": 0, "inProgress": 0, "missing": 1, "warn": 0},
        "notes": [],
    }
    result = list_mapping_release_readiness()
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["readyForPromotion"] is False
    assert item["status"] == "MISSING"
    assert any("No mapping definition" in b for b in item["blockers"])
    assert any("No fixtures" in b for b in item["blockers"])


@patch("schema.mapping_release_readiness.list_mapping_readiness")
def test_partial_mapping_returns_blockers(mock_readiness: object) -> None:
    """Partial/in-progress mapping returns blockers."""
    mock_readiness.return_value = {
        "items": [
            {
                "operationCode": "GET_MEMBER_ACCUMULATORS",
                "version": "1.0",
                "sourceVendor": "LH001",
                "targetVendor": "LH002",
                "mappingDefinition": True,
                "fixtures": False,
                "certification": False,
                "runtimeReady": True,
                "status": "IN_PROGRESS",
            },
        ],
        "summary": {"total": 1, "ready": 0, "inProgress": 1, "missing": 0, "warn": 0},
        "notes": [],
    }
    result = list_mapping_release_readiness()
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["readyForPromotion"] is False
    assert any("No fixtures" in b for b in item["blockers"])


@patch("schema.mapping_release_readiness.list_mapping_readiness")
def test_summary_counts_are_correct(mock_readiness: object) -> None:
    """Summary counts readyForPromotion and notReady correctly."""
    mock_readiness.return_value = {
        "items": [
            {
                "operationCode": "OP1",
                "version": "1.0",
                "sourceVendor": "LH001",
                "targetVendor": "LH002",
                "mappingDefinition": True,
                "fixtures": True,
                "certification": True,
                "runtimeReady": True,
                "status": "READY",
            },
            {
                "operationCode": "OP2",
                "version": "1.0",
                "sourceVendor": "LH001",
                "targetVendor": "LH003",
                "mappingDefinition": False,
                "fixtures": False,
                "certification": False,
                "runtimeReady": False,
                "status": "MISSING",
            },
        ],
        "summary": {"total": 2, "ready": 1, "inProgress": 0, "missing": 1, "warn": 0},
        "notes": [],
    }
    result = list_mapping_release_readiness()
    assert result["summary"]["total"] == 2
    assert result["summary"]["readyForPromotion"] == 1
    assert result["summary"]["notReady"] == 1


def test_report_includes_checklist_and_recommended_next_step() -> None:
    """Report includes releaseChecklist and recommendedNextStep."""
    payload = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
    }
    result = build_mapping_release_readiness_report(payload)
    assert result["valid"] is True
    report = result["report"]
    assert report is not None
    assert "releaseChecklist" in report
    assert len(report["releaseChecklist"]) >= 1
    assert "recommendedNextStep" in report
    assert "Manual code review" in report["recommendedNextStep"] or "Address blockers" in report["recommendedNextStep"]


def test_report_never_indicates_auto_applied_state() -> None:
    """Report notes never indicate auto-applied state."""
    payload = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
    }
    result = build_mapping_release_readiness_report(payload)
    assert result["valid"] is True
    report = result["report"]
    assert report is not None
    notes = " ".join(report.get("notes") or [])
    assert "auto" not in notes.lower() or "no" in notes.lower()
    assert "No code or runtime state was changed" in notes or "No runtime mapping was changed" in notes


def test_report_invalid_payload_returns_validation_error() -> None:
    """Invalid payload returns valid=False with notes."""
    result = build_mapping_release_readiness_report({})
    assert result["valid"] is False
    assert result["report"] is None
    assert "required" in (result.get("notes") or [""])[0].lower()


def test_markdown_endpoint_returns_markdown() -> None:
    """build_mapping_release_readiness_markdown returns markdown string."""
    payload = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
    }
    result = build_mapping_release_readiness_markdown(payload)
    assert result["valid"] is True
    assert "markdown" in result
    assert "GET_VERIFY_MEMBER_ELIGIBILITY" in result["markdown"]
    assert "Release Readiness" in result["markdown"]
