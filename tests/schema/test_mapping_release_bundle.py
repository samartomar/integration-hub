"""Tests for mapping_release_bundle service."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from schema.mapping_release_bundle import (
    build_mapping_release_bundle,
    build_mapping_release_bundle_markdown,
    list_release_bundle_candidates,
    summarize_mapping_release_bundle,
)


@patch("schema.mapping_release_bundle.list_mapping_release_readiness")
def test_list_release_bundle_candidates_includes_ready(mock_list: object) -> None:
    """Candidates list includes current READY mappings from release readiness."""
    mock_list.return_value = {
        "items": [
            {
                "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
                "version": "1.0",
                "sourceVendor": "LH001",
                "targetVendor": "LH002",
                "readyForPromotion": True,
                "status": "READY",
                "blockers": [],
                "evidence": {
                    "mappingDefinition": True,
                    "fixtures": True,
                    "certification": True,
                    "runtimeReady": True,
                },
            },
        ],
        "summary": {"total": 1, "readyForPromotion": 1, "notReady": 0},
    }
    result = list_release_bundle_candidates()
    assert len(result["items"]) == 1
    assert result["items"][0]["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert result["items"][0]["readyForPromotion"] is True


@patch("schema.mapping_release_bundle.get_mapping_readiness")
def test_bundle_generation_succeeds_for_ready_mappings(mock_get: object) -> None:
    """Bundle generation succeeds for LH001->LH002 current READY mappings."""
    mock_get.return_value = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mappingDefinition": True,
        "fixtures": True,
        "certification": True,
        "runtimeReady": True,
        "status": "READY",
        "notes": [],
    }
    payload = {
        "bundleName": "Release Candidate 2026-03-07",
        "items": [
            {
                "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
                "version": "1.0",
                "sourceVendor": "LH001",
                "targetVendor": "LH002",
            },
        ],
    }
    result = build_mapping_release_bundle(payload)
    assert result["valid"] is True
    bundle = result["bundle"]
    assert bundle is not None
    assert bundle["summary"]["included"] == 1
    assert bundle["summary"]["ready"] == 1
    assert bundle["summary"]["blocked"] == 0
    assert bundle["summary"]["status"] == "READY"
    assert len(bundle["items"]) == 1
    assert bundle["items"][0]["readyForPromotion"] is True
    assert "targetDefinitionFile" in bundle["items"][0]
    assert "impactedFiles" in bundle
    assert len(bundle["impactedFiles"]) == 1
    assert "verificationChecklist" in bundle
    assert len(bundle["verificationChecklist"]) > 0
    assert "Release bundle only" in (bundle.get("notes") or [""])[0]


@patch("schema.mapping_release_bundle.get_mapping_readiness")
def test_bundle_status_blocked_when_item_not_ready(mock_get: object) -> None:
    """Bundle status becomes BLOCKED when any selected item is not ready."""
    mock_get.return_value = {
        "operationCode": "GET_MEMBER_ACCUMULATORS",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mappingDefinition": True,
        "fixtures": False,
        "certification": False,
        "runtimeReady": True,
        "status": "IN_PROGRESS",
        "notes": ["No fixtures."],
    }
    payload = {
        "bundleName": "Partial Bundle",
        "items": [
            {
                "operationCode": "GET_MEMBER_ACCUMULATORS",
                "version": "1.0",
                "sourceVendor": "LH001",
                "targetVendor": "LH002",
            },
        ],
    }
    result = build_mapping_release_bundle(payload)
    assert result["valid"] is True
    bundle = result["bundle"]
    assert bundle["summary"]["status"] == "BLOCKED"
    assert bundle["summary"]["blocked"] == 1
    assert bundle["summary"]["ready"] == 0
    assert bundle["items"][0]["readyForPromotion"] is False
    assert len(bundle["items"][0]["blockers"]) > 0


@patch("schema.mapping_release_bundle.get_mapping_readiness")
def test_impacted_files_inferred_correctly(mock_get: object) -> None:
    """Impacted files are inferred correctly from operation/vendor pair."""
    mock_get.return_value = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mappingDefinition": True,
        "fixtures": True,
        "certification": True,
        "runtimeReady": True,
        "status": "READY",
        "notes": [],
    }
    payload = {
        "bundleName": "Test",
        "items": [
            {
                "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
                "version": "1.0",
                "sourceVendor": "LH001",
                "targetVendor": "LH002",
            },
        ],
    }
    result = build_mapping_release_bundle(payload)
    assert result["valid"] is True
    impacted = result["bundle"]["impactedFiles"]
    assert any("eligibility" in f and "lh001" in f and "lh002" in f for f in impacted)


@patch("schema.mapping_release_bundle.get_mapping_readiness")
def test_verification_checklist_present(mock_get: object) -> None:
    """Verification checklist is present in bundle."""
    mock_get.return_value = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mappingDefinition": True,
        "fixtures": True,
        "certification": True,
        "runtimeReady": True,
        "status": "READY",
        "notes": [],
    }
    payload = {
        "bundleName": "Test",
        "items": [
            {
                "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
                "version": "1.0",
                "sourceVendor": "LH001",
                "targetVendor": "LH002",
            },
        ],
    }
    result = build_mapping_release_bundle(payload)
    checklist = result["bundle"]["verificationChecklist"]
    assert "Review all included mapping definition changes" in " ".join(checklist)
    assert "Complete manual code review" in " ".join(checklist)


@patch("schema.mapping_release_bundle.get_mapping_readiness")
def test_bundle_never_indicates_applied(mock_get: object) -> None:
    """Bundle never indicates applied or runtime-changed state."""
    mock_get.return_value = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mappingDefinition": True,
        "fixtures": True,
        "certification": True,
        "runtimeReady": True,
        "status": "READY",
        "notes": [],
    }
    payload = {
        "bundleName": "Test",
        "items": [
            {
                "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
                "version": "1.0",
                "sourceVendor": "LH001",
                "targetVendor": "LH002",
            },
        ],
    }
    result = build_mapping_release_bundle(payload)
    notes = " ".join(result["bundle"].get("notes") or [])
    assert "No mappings were changed" in notes or "Release bundle only" in notes
    assert "applied" not in notes.lower() or "not" in notes.lower() or "no" in notes.lower()


def test_build_bundle_invalid_payload() -> None:
    """Invalid payload returns valid=False."""
    result = build_mapping_release_bundle({})
    assert result["valid"] is False
    assert result["bundle"] is None

    result = build_mapping_release_bundle({"items": []})
    assert result["valid"] is False


def test_build_bundle_missing_required_fields() -> None:
    """Item missing operationCode/sourceVendor/targetVendor returns validation error."""
    result = build_mapping_release_bundle({
        "bundleName": "Test",
        "items": [{"operationCode": "OP", "sourceVendor": "A"}],  # missing targetVendor
    })
    assert result["valid"] is False


def test_build_markdown_returns_string() -> None:
    """build_mapping_release_bundle_markdown returns markdown string."""
    bundle = {
        "bundleName": "Test Bundle",
        "bundleId": "abc-123",
        "createdAt": "2026-03-07T00:00:00Z",
        "summary": {"included": 1, "ready": 1, "blocked": 0, "status": "READY"},
        "items": [
            {
                "operationCode": "OP",
                "version": "1.0",
                "sourceVendor": "A",
                "targetVendor": "B",
                "readyForPromotion": True,
                "blockers": [],
            },
        ],
        "impactedFiles": ["path/to/file.py"],
        "verificationChecklist": ["Item 1"],
        "notes": ["Note"],
    }
    md = build_mapping_release_bundle_markdown(bundle)
    assert "# Test Bundle" in md
    assert "OP" in md
    assert "path/to/file.py" in md
    assert "Item 1" in md


def test_summarize_bundle() -> None:
    """summarize_mapping_release_bundle extracts summary."""
    bundle = {
        "summary": {"included": 3, "ready": 2, "blocked": 1, "status": "BLOCKED"},
    }
    s = summarize_mapping_release_bundle(bundle)
    assert s["included"] == 3
    assert s["ready"] == 2
    assert s["blocked"] == 1
    assert s["status"] == "BLOCKED"
