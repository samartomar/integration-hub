"""Envelope validation tests."""

from __future__ import annotations

import pytest

import jsonschema

from schema.canonical_validator import (
    validate_envelope,
    validate_request_envelope,
    validate_response_envelope,
)

OP = "GET_VERIFY_MEMBER_ELIGIBILITY"
VALID_TS = "2025-03-06T12:00:00Z"

VALID_REQUEST_ENV = {
    "operationCode": OP,
    "version": "1.0",
    "direction": "REQUEST",
    "correlationId": "corr-123",
    "timestamp": VALID_TS,
    "context": {},
    "payload": {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"},
}

VALID_RESPONSE_ENV = {
    "operationCode": OP,
    "version": "1.0",
    "direction": "RESPONSE",
    "correlationId": "corr-123",
    "timestamp": VALID_TS,
    "context": {},
    "payload": {
        "memberIdWithPrefix": "LH001-12345",
        "name": "Jane Doe",
        "dob": "1990-01-15",
        "status": "ACTIVE",
    },
}


def test_valid_request_envelope() -> None:
    """Valid request envelope passes."""
    validate_request_envelope(OP, VALID_REQUEST_ENV)


def test_valid_response_envelope() -> None:
    """Valid response envelope passes."""
    validate_response_envelope(OP, VALID_RESPONSE_ENV)


def test_invalid_envelope_missing_field() -> None:
    """Invalid envelope missing required field raises."""
    bad = {**VALID_REQUEST_ENV}
    del bad["correlationId"]
    with pytest.raises(jsonschema.ValidationError):
        validate_envelope(bad)


def test_invalid_envelope_bad_timestamp() -> None:
    """Invalid envelope with bad timestamp raises."""
    bad = {**VALID_REQUEST_ENV, "timestamp": "not-a-datetime"}
    with pytest.raises(jsonschema.ValidationError):
        validate_envelope(bad)


def test_invalid_request_envelope_wrong_direction() -> None:
    """validate_request_envelope rejects direction=RESPONSE."""
    bad = {**VALID_REQUEST_ENV, "direction": "RESPONSE"}
    with pytest.raises(jsonschema.ValidationError) as exc_info:
        validate_request_envelope(OP, bad)
    assert "REQUEST" in str(exc_info.value)


def test_invalid_response_envelope_wrong_direction() -> None:
    """validate_response_envelope rejects direction=REQUEST."""
    bad = {**VALID_RESPONSE_ENV, "direction": "REQUEST"}
    with pytest.raises(jsonschema.ValidationError) as exc_info:
        validate_response_envelope(OP, bad)
    assert "RESPONSE" in str(exc_info.value)


# --- GET_MEMBER_ACCUMULATORS envelopes ---

ACC_OP = "GET_MEMBER_ACCUMULATORS"
ACC_VALID_REQUEST_ENV = {
    "operationCode": ACC_OP,
    "version": "1.0",
    "direction": "REQUEST",
    "correlationId": "corr-acc",
    "timestamp": VALID_TS,
    "context": {},
    "payload": {"memberIdWithPrefix": "LH001-12345", "asOfDate": "2025-03-06"},
}
ACC_VALID_RESPONSE_ENV = {
    "operationCode": ACC_OP,
    "version": "1.0",
    "direction": "RESPONSE",
    "correlationId": "corr-acc",
    "timestamp": VALID_TS,
    "context": {},
    "payload": {
        "memberIdWithPrefix": "LH001-12345",
        "planYear": 2025,
        "currency": "USD",
        "individualDeductible": {"total": 2000, "used": 500, "remaining": 1500},
        "individualOutOfPocket": {"total": 8000, "used": 1200, "remaining": 6800},
    },
}


def test_accumulators_valid_request_envelope() -> None:
    """Valid accumulators request envelope passes."""
    validate_request_envelope(ACC_OP, ACC_VALID_REQUEST_ENV)


def test_accumulators_valid_response_envelope() -> None:
    """Valid accumulators response envelope passes."""
    validate_response_envelope(ACC_OP, ACC_VALID_RESPONSE_ENV)
