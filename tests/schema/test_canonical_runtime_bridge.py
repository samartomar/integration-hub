"""Unit tests for canonical_runtime_bridge."""

from __future__ import annotations

import pytest

from schema.canonical_runtime_bridge import (
    build_execute_request_from_canonical,
    run_canonical_bridge,
    validate_bridge_request,
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


def test_build_execute_request_from_canonical_returns_correct_shape() -> None:
    """build_execute_request_from_canonical returns targetVendor, operation, parameters, idempotencyKey."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "DRY_RUN",
        "envelope": _eligibility_envelope(),
    }
    req = build_execute_request_from_canonical(payload)
    assert req is not None
    assert req["targetVendor"] == "LH002"
    assert req["operation"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert req["parameters"] == {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"}
    assert req.get("idempotencyKey") == "corr-test"


def test_build_execute_request_from_canonical_invalid_returns_none() -> None:
    """Invalid payload returns None."""
    payload = {"sourceVendor": "LH001", "targetVendor": "LH002", "mode": "DRY_RUN"}
    assert build_execute_request_from_canonical(payload) is None


def test_run_canonical_bridge_dry_run_returns_preview() -> None:
    """DRY_RUN mode returns preflight + executeRequestPreview + executionPlan."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "DRY_RUN",
        "envelope": _eligibility_envelope(),
    }
    result = run_canonical_bridge(payload)
    assert result["mode"] == "DRY_RUN"
    assert "preflight" in result
    assert "executeRequestPreview" in result
    assert "executionPlan" in result
    assert result["valid"] is True
    assert result["status"] == "READY"


def test_run_canonical_bridge_execute_without_executor_returns_failed() -> None:
    """EXECUTE mode without executor returns FAILED."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }
    result = run_canonical_bridge(payload)
    assert result["mode"] == "EXECUTE"
    assert result["valid"] is False
    assert result["status"] == "FAILED"
    assert "Executor not provided" in str(result.get("executeResult", {}).get("error", ""))


def test_run_canonical_bridge_execute_with_executor_calls_it() -> None:
    """EXECUTE mode with executor calls it and returns result."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }
    called = []

    def mock_executor(req: dict) -> dict:
        called.append(req)
        return {"statusCode": 200, "body": '{"transactionId":"tx-123"}'}

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert len(called) == 1
    assert called[0]["targetVendor"] == "LH002"
    assert called[0]["operation"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert result["status"] == "EXECUTED"
    assert result["executeResult"]["statusCode"] == 200


def test_run_canonical_bridge_blocked_preflight_returns_blocked() -> None:
    """When preflight blocks, bridge returns BLOCKED without executing."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": {
            "operationCode": "UNKNOWN_OP_XYZ",
            "version": "1.0",
            "direction": "REQUEST",
            "correlationId": "corr",
            "timestamp": "2025-03-06T12:00:00Z",
            "context": {},
            "payload": {},
        },
    }
    executor_called = []

    def mock_executor(req: dict) -> dict:
        executor_called.append(req)
        return {"statusCode": 200, "body": "{}"}

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "BLOCKED"
    assert result["valid"] is False
    assert len(executor_called) == 0


def test_validate_bridge_request_requires_mode() -> None:
    """validate_bridge_request requires mode DRY_RUN or EXECUTE."""
    errors = validate_bridge_request({
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "envelope": _eligibility_envelope(),
    })
    assert any("mode" in (e.get("field") or "") for e in errors)
