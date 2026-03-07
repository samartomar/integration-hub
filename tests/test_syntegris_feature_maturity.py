"""Consolidated tests for Syntegris production-maturity path."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_src = Path(__file__).resolve().parent.parent / "apps" / "api" / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from shared.feature_runtime_diagnostics import get_syntegris_feature_diagnostics
from schema.mapping_release_bundle import (
    build_mapping_release_bundle,
    list_release_bundle_candidates,
)


def test_diagnostics_does_not_expose_secrets() -> None:
    """Diagnostics response must not contain secret values."""
    result = get_syntegris_feature_diagnostics()
    assert "status" in result
    assert "checks" in result
    assert "notes" in result
    for check in result.get("checks") or []:
        msg = (check.get("message") or "").lower()
        assert "password" not in msg
        assert "secret" not in msg or "not expose" in (result.get("notes") or [""])[0].lower()
    assert any("secrets" in (n or "").lower() for n in result.get("notes") or [])


@patch("schema.mapping_release_bundle.list_mapping_release_readiness")
def test_release_bundle_candidates_includes_ready(mock_list: object) -> None:
    """Candidates include current READY mappings from release readiness."""
    mock_list.return_value = {
        "items": [
            {
                "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
                "version": "1.0",
                "sourceVendor": "LH001",
                "targetVendor": "LH002",
                "readyForPromotion": True,
                "status": "READY",
            },
        ],
        "summary": {"total": 1, "readyForPromotion": 1, "notReady": 0},
    }
    result = list_release_bundle_candidates()
    assert len(result["items"]) == 1
    assert result["items"][0]["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert result["items"][0]["readyForPromotion"] is True


@patch("schema.mapping_release_bundle.get_mapping_readiness")
def test_release_bundle_generation_for_lh001_lh002(mock_get: object) -> None:
    """Release bundle generation works for LH001->LH002 supported mappings."""
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
        "bundleName": "Release Candidate - LH001-LH002",
        "items": [
            {"operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY", "version": "1.0", "sourceVendor": "LH001", "targetVendor": "LH002"},
        ],
    }
    result = build_mapping_release_bundle(payload)
    assert result["valid"] is True
    bundle = result.get("bundle")
    assert bundle is not None
    assert bundle["summary"]["included"] == 1
    assert bundle["summary"]["ready"] == 1
    assert bundle["summary"]["status"] == "READY"
    assert "eligibility_v1_lh001_lh002.py" in str(bundle.get("impactedFiles", []))
