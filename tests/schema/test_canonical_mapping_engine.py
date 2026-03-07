"""Unit tests for canonical mapping engine."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "apps" / "api" / "src"))

from schema.canonical_mapping_engine import (
    list_mapping_operations,
    get_mapping_definition,
    validate_mapping_definition,
    transform_canonical_to_vendor,
    transform_vendor_to_canonical,
    preview_mapping,
    validate_mapping_request,
)


def test_list_operations_with_mappings_works() -> None:
    """list_mapping_operations returns operations that have mapping definitions."""
    items = list_mapping_operations()
    assert len(items) >= 2
    op_codes = {i["operationCode"] for i in items}
    assert "GET_VERIFY_MEMBER_ELIGIBILITY" in op_codes
    assert "GET_MEMBER_ACCUMULATORS" in op_codes
    for item in items:
        assert "operationCode" in item
        assert "version" in item
        assert "vendorPairs" in item


def test_eligibility_canonical_to_vendor_preview_works() -> None:
    """Eligibility canonical->vendor preview works."""
    payload = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "inputPayload": {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"},
    }
    result = preview_mapping(payload)
    assert result["valid"] is True
    assert result["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert result["direction"] == "CANONICAL_TO_VENDOR"
    assert result["outputPayload"] == {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"}
    assert "executeResult" not in result


def test_eligibility_vendor_to_canonical_preview_works() -> None:
    """Eligibility vendor->canonical preview works."""
    payload = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "VENDOR_TO_CANONICAL",
        "inputPayload": {
            "memberIdWithPrefix": "LH001-12345",
            "name": "Jane Doe",
            "dob": "1990-01-15",
            "claimNumber": "CLM-789",
            "dateOfService": "2025-03-06",
            "status": "ACTIVE",
        },
    }
    result = preview_mapping(payload)
    assert result["valid"] is True
    assert result["outputPayload"]["memberIdWithPrefix"] == "LH001-12345"
    assert result["outputPayload"]["name"] == "Jane Doe"
    assert result["outputPayload"]["status"] == "ACTIVE"


def test_accumulators_canonical_to_vendor_preview_works() -> None:
    """Accumulators canonical->vendor preview works."""
    payload = {
        "operationCode": "GET_MEMBER_ACCUMULATORS",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "inputPayload": {"memberIdWithPrefix": "LH001-12345", "asOfDate": "2025-03-06"},
    }
    result = preview_mapping(payload)
    assert result["valid"] is True
    assert result["outputPayload"] == {"memberIdWithPrefix": "LH001-12345", "asOfDate": "2025-03-06"}


def test_accumulators_vendor_to_canonical_preview_works() -> None:
    """Accumulators vendor->canonical preview works."""
    payload = {
        "operationCode": "GET_MEMBER_ACCUMULATORS",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "VENDOR_TO_CANONICAL",
        "inputPayload": {
            "memberIdWithPrefix": "LH001-12345",
            "planYear": 2025,
            "currency": "USD",
            "individualDeductible": {"total": 2000, "used": 500, "remaining": 1500},
            "familyDeductible": {"total": 4000, "used": 500, "remaining": 3500},
            "individualOutOfPocket": {"total": 8000, "used": 1200, "remaining": 6800},
            "familyOutOfPocket": {"total": 16000, "used": 1200, "remaining": 14800},
        },
    }
    result = preview_mapping(payload)
    assert result["valid"] is True
    assert result["outputPayload"]["memberIdWithPrefix"] == "LH001-12345"
    assert result["outputPayload"]["planYear"] == 2025
    assert result["outputPayload"]["individualDeductible"]["total"] == 2000


def test_alias_version_v1_normalizes_to_1_0() -> None:
    """Alias version v1 normalizes to 1.0."""
    payload = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "v1",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "inputPayload": {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"},
    }
    result = preview_mapping(payload)
    assert result["valid"] is True
    assert result["version"] == "1.0"


def test_missing_required_input_field_yields_validation_failure() -> None:
    """Missing required input field yields clear validation failure."""
    payload = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "inputPayload": {"memberIdWithPrefix": "LH001-12345"},  # missing date
    }
    result = preview_mapping(payload)
    assert result["valid"] is False
    assert "errors" in result
    assert any("missing" in str(e).lower() for e in result["errors"])


def test_missing_mapping_definition_fails_clearly() -> None:
    """Missing mapping definition fails clearly."""
    payload = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH003",  # no mapping for LH003->LH004
        "targetVendor": "LH004",
        "direction": "CANONICAL_TO_VENDOR",
        "inputPayload": {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"},
    }
    result = preview_mapping(payload)
    assert result["valid"] is False
    assert "No mapping definition" in str(result.get("errors", []))


def test_preview_never_executes_runtime() -> None:
    """Preview never executes runtime - no executeResult or similar."""
    payload = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "direction": "CANONICAL_TO_VENDOR",
        "inputPayload": {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"},
    }
    result = preview_mapping(payload)
    assert "executeResult" not in result
    assert "transactionId" not in result


def test_get_mapping_definition_returns_none_for_unknown_pair() -> None:
    """get_mapping_definition returns None for unknown vendor pair."""
    assert get_mapping_definition("GET_VERIFY_MEMBER_ELIGIBILITY", "1.0", "LH003", "LH004") is None


def test_validate_mapping_definition_valid() -> None:
    """validate_mapping_definition accepts valid definition."""
    defn = {"canonicalToVendor": {"a": "$.b"}, "vendorToCanonical": {"x": "$.y"}}
    result = validate_mapping_definition(defn)
    assert result["valid"] is True


def test_validate_mapping_definition_invalid() -> None:
    """validate_mapping_definition rejects invalid definition."""
    result = validate_mapping_definition({"canonicalToVendor": "not an object"})
    assert result["valid"] is False
    assert "canonicalToVendor" in str(result.get("errors", []))
