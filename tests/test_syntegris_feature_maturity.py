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
from shared.supported_operation_slice import (
    SUPPORTED_OPERATIONS,
    SUPPORTED_SOURCE_VENDOR,
    SUPPORTED_TARGET_VENDOR,
    is_supported_canonical_slice,
    list_supported_canonical_operations,
)
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


def test_supported_operation_slice_helpers() -> None:
    """Supported slice helpers return correct values for cutover scope."""
    ops = list_supported_canonical_operations()
    assert "GET_VERIFY_MEMBER_ELIGIBILITY" in ops
    assert "GET_MEMBER_ACCUMULATORS" in ops
    assert len(ops) == 2
    assert "GET_VERIFY_MEMBER_ELIGIBILITY" in SUPPORTED_OPERATIONS
    assert SUPPORTED_SOURCE_VENDOR == "LH001"
    assert SUPPORTED_TARGET_VENDOR == "LH002"


def test_is_supported_canonical_slice() -> None:
    """is_supported_canonical_slice gates by operation and vendor pair."""
    assert is_supported_canonical_slice("GET_VERIFY_MEMBER_ELIGIBILITY", "LH001", "LH002") is True
    assert is_supported_canonical_slice("GET_MEMBER_ACCUMULATORS", "LH001", "LH002") is True
    assert is_supported_canonical_slice("GET_VERIFY_MEMBER_ELIGIBILITY", "LH001", "LH003") is False
    assert is_supported_canonical_slice("GET_OTHER_OP", "LH001", "LH002") is False
    assert is_supported_canonical_slice("GET_VERIFY_MEMBER_ELIGIBILITY") is True
