"""Tests for mapping readiness service."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "apps" / "api" / "src"))

from schema.mapping_readiness import (
    get_mapping_readiness,
    list_mapping_readiness,
    summarize_mapping_readiness,
)


def test_implemented_lh001_lh002_eligibility_is_ready() -> None:
    """Current implemented LH001->LH002 eligibility mapping returns READY."""
    item = get_mapping_readiness(
        "GET_VERIFY_MEMBER_ELIGIBILITY", "1.0", "LH001", "LH002"
    )
    assert item["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert item["version"] == "1.0"
    assert item["sourceVendor"] == "LH001"
    assert item["targetVendor"] == "LH002"
    assert item["mappingDefinition"] is True
    assert item["fixtures"] is True
    assert item["certification"] is True
    assert item["runtimeReady"] is True
    assert item["status"] == "READY"


def test_implemented_lh001_lh002_accumulators_is_ready() -> None:
    """Current implemented LH001->LH002 accumulators mapping returns READY."""
    item = get_mapping_readiness(
        "GET_MEMBER_ACCUMULATORS", "1.0", "LH001", "LH002"
    )
    assert item["operationCode"] == "GET_MEMBER_ACCUMULATORS"
    assert item["mappingDefinition"] is True
    assert item["fixtures"] is True
    assert item["status"] == "READY"


def test_missing_mapping_returns_missing() -> None:
    """Missing mapping definition returns MISSING."""
    with patch(
        "schema.mapping_readiness.get_mapping_definition",
        return_value=None,
    ):
        with patch(
            "schema.mapping_readiness.list_mapping_fixtures",
            return_value=[],
        ):
            item = get_mapping_readiness(
                "GET_VERIFY_MEMBER_ELIGIBILITY", "1.0", "LH999", "LH998"
            )
    assert item["status"] == "MISSING"
    assert item["mappingDefinition"] is False
    assert item["fixtures"] is False


def test_partial_artifacts_returns_in_progress() -> None:
    """Mapping exists but no fixtures returns IN_PROGRESS."""
    with patch(
        "schema.mapping_readiness.get_mapping_definition",
        return_value={"canonicalToVendor": {}, "vendorToCanonical": {}},
    ):
        with patch(
            "schema.mapping_readiness.list_mapping_fixtures",
            return_value=[],
        ):
            item = get_mapping_readiness(
                "GET_VERIFY_MEMBER_ELIGIBILITY", "1.0", "LH001", "LH002"
            )
    assert item["status"] == "IN_PROGRESS"
    assert item["mappingDefinition"] is True
    assert item["fixtures"] is False


def test_certification_fail_returns_warn() -> None:
    """Mapping and fixtures exist but certification fails returns WARN."""
    with patch(
        "schema.mapping_readiness.get_mapping_definition",
        return_value={"canonicalToVendor": {}, "vendorToCanonical": {}},
    ):
        with patch(
            "schema.mapping_readiness.list_mapping_fixtures",
            return_value=[{"fixtureId": "f1", "direction": "CANONICAL_TO_VENDOR"}],
        ):
            with patch(
                "schema.mapping_readiness.run_mapping_certification",
                return_value={
                    "valid": False,
                    "summary": {"status": "FAIL", "failed": 1},
                },
            ):
                item = get_mapping_readiness(
                    "GET_VERIFY_MEMBER_ELIGIBILITY", "1.0", "LH001", "LH002"
                )
    assert item["status"] == "WARN"
    assert item["mappingDefinition"] is True
    assert item["fixtures"] is True


def test_list_mapping_readiness_returns_items() -> None:
    """list_mapping_readiness returns items and summary."""
    result = list_mapping_readiness()
    assert "items" in result
    assert "summary" in result
    assert "notes" in result
    assert result["summary"]["total"] >= 2
    assert result["summary"]["ready"] >= 2


def test_list_mapping_readiness_filter_by_operation() -> None:
    """Filter by operationCode works."""
    result = list_mapping_readiness({"operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY"})
    assert all(
        i["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
        for i in result["items"]
    )


def test_list_mapping_readiness_filter_by_status() -> None:
    """Filter by status works."""
    result = list_mapping_readiness({"status": "READY"})
    assert all(i["status"] == "READY" for i in result["items"])


def test_summarize_mapping_readiness_counts() -> None:
    """Summary counts are correct."""
    items = [
        {"status": "READY"},
        {"status": "READY"},
        {"status": "IN_PROGRESS"},
        {"status": "MISSING"},
    ]
    summary = summarize_mapping_readiness(items)
    assert summary["total"] == 4
    assert summary["ready"] == 2
    assert summary["inProgress"] == 1
    assert summary["missing"] == 1
    assert summary["warn"] == 0
