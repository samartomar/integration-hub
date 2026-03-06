"""Payload validation tests for canonical_validator."""

from __future__ import annotations

import pytest

import jsonschema

from schema.canonical_validator import validate_request, validate_response

OP = "GET_VERIFY_MEMBER_ELIGIBILITY"

VALID_REQUEST = {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"}
VALID_RESPONSE = {
    "memberIdWithPrefix": "LH001-12345",
    "name": "Jane Doe",
    "dob": "1990-01-15",
    "status": "ACTIVE",
}


def test_valid_request() -> None:
    """Valid request passes validation."""
    validate_request(OP, VALID_REQUEST)


def test_invalid_request_missing_member_id() -> None:
    """Invalid request missing memberIdWithPrefix raises."""
    with pytest.raises(jsonschema.ValidationError):
        validate_request(OP, {"date": "2025-03-06"})


def test_invalid_request_bad_date() -> None:
    """Invalid request with bad date format raises."""
    with pytest.raises(jsonschema.ValidationError):
        validate_request(OP, {"memberIdWithPrefix": "X", "date": "03-06-2025"})
    with pytest.raises(jsonschema.ValidationError):
        validate_request(OP, {"memberIdWithPrefix": "X", "date": "invalid"})


def test_valid_response() -> None:
    """Valid response passes validation."""
    validate_response(OP, VALID_RESPONSE)


def test_invalid_response_bad_status() -> None:
    """Invalid response with bad status enum raises."""
    bad = {**VALID_RESPONSE, "status": "INVALID_STATUS"}
    with pytest.raises(jsonschema.ValidationError):
        validate_response(OP, bad)


def test_validate_request_with_version_alias() -> None:
    """validate_request works with version alias v1."""
    validate_request(OP, VALID_REQUEST, version="v1")


def test_validate_response_with_version_alias() -> None:
    """validate_response works with version alias v1."""
    validate_response(OP, VALID_RESPONSE, version="v1")


# --- GET_MEMBER_ACCUMULATORS ---

ACC_OP = "GET_MEMBER_ACCUMULATORS"
ACC_VALID_REQUEST = {"memberIdWithPrefix": "LH001-12345", "asOfDate": "2025-03-06"}
ACC_VALID_RESPONSE = {
    "memberIdWithPrefix": "LH001-12345",
    "planYear": 2025,
    "currency": "USD",
    "individualDeductible": {"total": 2000, "used": 500, "remaining": 1500},
    "familyDeductible": {"total": 4000, "used": 500, "remaining": 3500},
    "individualOutOfPocket": {"total": 8000, "used": 1200, "remaining": 6800},
    "familyOutOfPocket": {"total": 16000, "used": 1200, "remaining": 14800},
}


def test_accumulators_valid_request() -> None:
    """Valid accumulators request passes validation."""
    validate_request(ACC_OP, ACC_VALID_REQUEST)


def test_accumulators_invalid_as_of_date() -> None:
    """Invalid asOfDate format raises."""
    with pytest.raises(jsonschema.ValidationError):
        validate_request(ACC_OP, {"memberIdWithPrefix": "X", "asOfDate": "03-06-2025"})
    with pytest.raises(jsonschema.ValidationError):
        validate_request(ACC_OP, {"memberIdWithPrefix": "X", "asOfDate": "invalid"})


def test_accumulators_valid_response_with_nested() -> None:
    """Valid accumulators response with nested objects passes."""
    validate_response(ACC_OP, ACC_VALID_RESPONSE)


def test_accumulators_invalid_response_missing_nested_field() -> None:
    """Invalid response missing required nested field raises."""
    bad = {**ACC_VALID_RESPONSE}
    bad["individualDeductible"] = {"total": 2000, "used": 500}  # missing remaining
    with pytest.raises(jsonschema.ValidationError):
        validate_response(ACC_OP, bad)


def test_accumulators_invalid_response_wrong_numeric_type() -> None:
    """Invalid response with wrong numeric type in nested object raises."""
    bad = {**ACC_VALID_RESPONSE}
    bad["individualDeductible"] = {"total": "2000", "used": 500, "remaining": 1500}
    with pytest.raises(jsonschema.ValidationError):
        validate_response(ACC_OP, bad)
