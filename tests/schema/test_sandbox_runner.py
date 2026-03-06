"""Unit tests for sandbox_runner - mock-safe canonical sandbox helpers."""

from __future__ import annotations

import pytest

from schema.sandbox_runner import (
    build_sandbox_request_envelope,
    get_sandbox_operation,
    list_sandbox_operations,
    run_mock_sandbox_test,
    validate_sandbox_request,
)

ELIGIBILITY_OP = "GET_VERIFY_MEMBER_ELIGIBILITY"
ACCUMULATORS_OP = "GET_MEMBER_ACCUMULATORS"
ELIGIBILITY_VALID = {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"}
ACCUMULATORS_VALID = {"memberIdWithPrefix": "LH001-12345", "asOfDate": "2025-03-06"}


def test_list_sandbox_operations_returns_both_ops() -> None:
    """list_sandbox_operations returns both canonical operations."""
    items = list_sandbox_operations()
    ops = {item["operationCode"]: item for item in items}
    assert ELIGIBILITY_OP in ops
    assert ACCUMULATORS_OP in ops
    assert ops[ELIGIBILITY_OP]["latestVersion"] == "1.0"
    assert ops[ACCUMULATORS_OP]["latestVersion"] == "1.0"


def test_get_sandbox_operation_exact_version() -> None:
    """get_sandbox_operation works for exact version 1.0."""
    op = get_sandbox_operation(ELIGIBILITY_OP, "1.0")
    assert op is not None
    assert op["operationCode"] == ELIGIBILITY_OP
    assert op["version"] == "1.0"
    assert "requestPayloadSchema" in op
    assert "examples" in op


def test_get_sandbox_operation_alias_v1() -> None:
    """get_sandbox_operation resolves version alias v1 to 1.0."""
    op = get_sandbox_operation(ELIGIBILITY_OP, "v1")
    assert op is not None
    assert op["version"] == "1.0"


def test_validate_sandbox_request_eligibility_valid() -> None:
    """validate_sandbox_request passes for valid eligibility request."""
    validate_sandbox_request(ELIGIBILITY_OP, ELIGIBILITY_VALID)


def test_validate_sandbox_request_eligibility_invalid_date() -> None:
    """validate_sandbox_request fails for invalid eligibility date."""
    import jsonschema

    with pytest.raises(jsonschema.ValidationError):
        validate_sandbox_request(
            ELIGIBILITY_OP,
            {"memberIdWithPrefix": "X", "date": "03-06-2025"},
        )


def test_validate_sandbox_request_accumulators_valid() -> None:
    """validate_sandbox_request passes for valid accumulators request."""
    validate_sandbox_request(ACCUMULATORS_OP, ACCUMULATORS_VALID)


def test_build_sandbox_request_envelope_valid() -> None:
    """build_sandbox_request_envelope creates valid request envelope."""
    envelope = build_sandbox_request_envelope(ELIGIBILITY_OP, ELIGIBILITY_VALID)
    assert envelope["operationCode"] == ELIGIBILITY_OP
    assert envelope["version"] == "1.0"
    assert envelope["direction"] == "REQUEST"
    assert envelope["payload"] == ELIGIBILITY_VALID
    assert "correlationId" in envelope
    assert "timestamp" in envelope


def test_run_mock_sandbox_test_eligibility_success() -> None:
    """run_mock_sandbox_test returns valid mock result for eligibility."""
    result = run_mock_sandbox_test(ELIGIBILITY_OP, ELIGIBILITY_VALID)
    assert result["operationCode"] == ELIGIBILITY_OP
    assert result["version"] == "1.0"
    assert result["mode"] == "MOCK"
    assert result["valid"] is True
    assert result["requestPayloadValid"] is True
    assert result["requestEnvelopeValid"] is True
    assert result["responseEnvelopeValid"] is True
    assert "requestEnvelope" in result
    assert "responseEnvelope" in result
    assert result["requestEnvelope"]["direction"] == "REQUEST"
    assert result["responseEnvelope"]["direction"] == "RESPONSE"
    assert "notes" in result


def test_run_mock_sandbox_test_accumulators_success() -> None:
    """run_mock_sandbox_test returns valid mock result for accumulators."""
    result = run_mock_sandbox_test(ACCUMULATORS_OP, ACCUMULATORS_VALID)
    assert result["operationCode"] == ACCUMULATORS_OP
    assert result["valid"] is True
    assert "requestEnvelope" in result
    assert "responseEnvelope" in result


def test_run_mock_sandbox_test_invalid_payload_returns_structured_failure() -> None:
    """Invalid payload returns structured failure and does not produce invalid envelopes."""
    result = run_mock_sandbox_test(
        ELIGIBILITY_OP,
        {"memberIdWithPrefix": "X", "date": "bad-date"},
    )
    assert result["valid"] is False
    assert "errors" in result
    assert len(result["errors"]) > 0
    assert result["requestPayloadValid"] is False
    assert "requestEnvelope" not in result or result.get("requestEnvelope") == {}
