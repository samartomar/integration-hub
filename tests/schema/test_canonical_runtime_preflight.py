"""Unit tests for canonical_runtime_preflight."""

from __future__ import annotations

import pytest

from schema.canonical_runtime_preflight import (
    run_canonical_preflight,
    validate_preflight_request,
)


def _eligibility_envelope(version: str = "1.0") -> dict:
    return {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": version,
        "direction": "REQUEST",
        "correlationId": "corr-test",
        "timestamp": "2025-03-06T12:00:00Z",
        "context": {},
        "payload": {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"},
    }


def _accumulators_envelope() -> dict:
    return {
        "operationCode": "GET_MEMBER_ACCUMULATORS",
        "version": "1.0",
        "direction": "REQUEST",
        "correlationId": "corr-test",
        "timestamp": "2025-03-06T12:00:00Z",
        "context": {},
        "payload": {"memberIdWithPrefix": "LH001-12345", "asOfDate": "2025-03-06"},
    }


def test_valid_eligibility_preflight_returns_ready() -> None:
    """Valid eligibility preflight returns READY or WARN with normalized version 1.0."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": _eligibility_envelope(),
    }
    result = run_canonical_preflight(payload)
    assert result["valid"] is True
    assert result["status"] in ("READY", "WARN")
    assert result["canonicalVersion"] == "1.0"
    assert result["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert any(c["code"] == "CANONICAL_OPERATION_RESOLVED" and c["status"] == "PASS" for c in result["checks"])
    assert any(c["code"] == "CANONICAL_REQUEST_VALID" and c["status"] == "PASS" for c in result["checks"])


def test_valid_accumulators_preflight_returns_ready() -> None:
    """Valid accumulators preflight returns READY or WARN."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": _accumulators_envelope(),
    }
    result = run_canonical_preflight(payload)
    assert result["valid"] is True
    assert result["status"] in ("READY", "WARN")
    assert result["operationCode"] == "GET_MEMBER_ACCUMULATORS"
    assert result["canonicalVersion"] == "1.0"


def test_alias_version_v1_resolves_to_1_0() -> None:
    """Alias version v1 resolves to 1.0."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": _eligibility_envelope(version="v1"),
    }
    result = run_canonical_preflight(payload)
    assert result["valid"] is True
    assert result["canonicalVersion"] == "1.0"
    assert result.get("normalizedEnvelope", {}).get("version") == "1.0"


def test_invalid_envelope_direction_fails() -> None:
    """Invalid envelope direction fails."""
    envelope = _eligibility_envelope()
    envelope["direction"] = "RESPONSE"
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": envelope,
    }
    result = run_canonical_preflight(payload)
    assert result["valid"] is False
    assert result["status"] == "BLOCKED"
    assert any("direction" in (c.get("message") or "").lower() for c in result["checks"])


def test_invalid_date_fails() -> None:
    """Invalid date fails."""
    envelope = _eligibility_envelope()
    envelope["payload"]["date"] = "03-06-2025"
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": envelope,
    }
    result = run_canonical_preflight(payload)
    assert result["valid"] is False
    assert result["status"] == "BLOCKED"
    assert any(c["code"] == "CANONICAL_REQUEST_VALID" and c["status"] == "FAIL" for c in result["checks"])


def test_unknown_operation_fails() -> None:
    """Unknown operation fails."""
    envelope = _eligibility_envelope()
    envelope["operationCode"] = "UNKNOWN_OP_XYZ"
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": envelope,
    }
    result = run_canonical_preflight(payload)
    assert result["valid"] is False
    assert result["status"] == "BLOCKED"
    assert any(c["code"] == "CANONICAL_OPERATION_RESOLVED" and c["status"] == "FAIL" for c in result["checks"])


def test_missing_source_vendor_fails() -> None:
    """Missing sourceVendor fails."""
    payload = {
        "sourceVendor": "",
        "targetVendor": "LH002",
        "envelope": _eligibility_envelope(),
    }
    result = run_canonical_preflight(payload)
    assert result["valid"] is False
    assert result["status"] == "BLOCKED"
    assert "errors" in result
    assert any("sourceVendor" in (e.get("field") or "") for e in result["errors"])


def test_missing_target_vendor_fails() -> None:
    """Missing targetVendor fails."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "",
        "envelope": _eligibility_envelope(),
    }
    result = run_canonical_preflight(payload)
    assert result["valid"] is False
    assert result["status"] == "BLOCKED"
    assert any("targetVendor" in (e.get("field") or "") for e in result["errors"])


def test_allowlist_ok_passes() -> None:
    """When allowlist_ok=True, VENDOR_PAIR_ALLOWED check passes."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": _eligibility_envelope(),
    }
    result = run_canonical_preflight(payload, allowlist_ok=True)
    assert result["valid"] is True
    assert any(c["code"] == "VENDOR_PAIR_ALLOWED" and c["status"] == "PASS" for c in result["checks"])


def test_allowlist_not_ok_blocks() -> None:
    """When allowlist_ok=False, status is BLOCKED."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": _eligibility_envelope(),
    }
    result = run_canonical_preflight(payload, allowlist_ok=False)
    assert result["valid"] is False
    assert result["status"] == "BLOCKED"
    assert any(c["code"] == "VENDOR_PAIR_ALLOWED" and c["status"] == "FAIL" for c in result["checks"])


def test_validate_preflight_request_empty_source() -> None:
    """validate_preflight_request returns errors for empty sourceVendor."""
    errors = validate_preflight_request({
        "sourceVendor": "",
        "targetVendor": "LH002",
        "envelope": {},
    })
    assert any("sourceVendor" in (e.get("field") or "") for e in errors)


def test_validate_preflight_request_missing_envelope() -> None:
    """validate_preflight_request returns errors for missing envelope."""
    errors = validate_preflight_request({
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
    })
    assert any("envelope" in (e.get("field") or "") for e in errors)
