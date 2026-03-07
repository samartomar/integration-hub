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


def test_dry_run_includes_vendor_request_preview() -> None:
    """DRY_RUN for mapped vendor pair includes mappingSummary and vendorRequestPreview."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "DRY_RUN",
        "envelope": _eligibility_envelope(),
    }
    result = run_canonical_bridge(payload)
    assert result["mode"] == "DRY_RUN"
    assert result["valid"] is True
    assert "mappingSummary" in result
    assert result["mappingSummary"].get("available") is True
    assert "vendorRequestPreview" in result
    assert result["vendorRequestPreview"] == {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"}


def test_execute_with_response_body_sets_canonical_response_envelope() -> None:
    """EXECUTE when executor returns body.responseBody sets canonicalResponseEnvelope."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }
    exec_response = {
        "statusCode": 200,
        "body": '{"transactionId":"tx-1","responseBody":{"memberIdWithPrefix":"LH001-12345","name":"Jane","status":"eligible"}}',
    }

    def mock_executor(req: dict) -> dict:
        return exec_response

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert "canonicalResponseEnvelope" in result
    assert result["canonicalResponseEnvelope"]["memberIdWithPrefix"] == "LH001-12345"
    assert result["canonicalResponseEnvelope"]["name"] == "Jane"


def test_execute_without_response_body_no_canonical_envelope() -> None:
    """EXECUTE when body has no responseBody does not set canonicalResponseEnvelope."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }

    def mock_executor(req: dict) -> dict:
        return {"statusCode": 200, "body": '{"transactionId":"tx-1"}'}

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert result.get("canonicalResponseEnvelope") is None


def test_dry_run_includes_vendor_request_preview() -> None:
    """DRY_RUN includes mappingSummary and vendorRequestPreview for mapped vendor pair."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "DRY_RUN",
        "envelope": _eligibility_envelope(),
    }
    result = run_canonical_bridge(payload)
    assert result["mode"] == "DRY_RUN"
    assert result["valid"] is True
    assert "mappingSummary" in result
    assert result["mappingSummary"].get("available") is True
    assert "vendorRequestPreview" in result
    assert result["vendorRequestPreview"].get("memberIdWithPrefix") == "LH001-12345"


def test_execute_with_response_body_sets_canonical_response_envelope() -> None:
    """When executor returns body with responseBody, bridge sets canonicalResponseEnvelope."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }
    mock_body = {
        "transactionId": "tx-123",
        "responseBody": {"memberIdWithPrefix": "LH001-12345", "name": "Jane", "status": "eligible"},
    }

    def mock_executor(req: dict) -> dict:
        return {"statusCode": 200, "body": mock_body}

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert "canonicalResponseEnvelope" in result
    assert result["canonicalResponseEnvelope"] == mock_body["responseBody"]


def test_execute_without_response_body_no_canonical_envelope() -> None:
    """When body has no responseBody, canonicalResponseEnvelope is not set."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }

    def mock_executor(req: dict) -> dict:
        return {"statusCode": 200, "body": {"transactionId": "tx-123", "status": "completed"}}

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert "canonicalResponseEnvelope" not in result or result.get("canonicalResponseEnvelope") is None


def test_dry_run_includes_vendor_request_preview() -> None:
    """DRY_RUN for mapped vendor pair includes mappingSummary and vendorRequestPreview."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "DRY_RUN",
        "envelope": _eligibility_envelope(),
    }
    result = run_canonical_bridge(payload)
    assert result["mode"] == "DRY_RUN"
    assert result["valid"] is True
    assert "mappingSummary" in result
    assert result["mappingSummary"].get("available") is True
    assert "vendorRequestPreview" in result
    assert result["vendorRequestPreview"] == {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"}


def test_execute_with_response_body_sets_canonical_response_envelope() -> None:
    """When executor returns body with responseBody, bridge sets canonicalResponseEnvelope."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }
    mock_response = {
        "statusCode": 200,
        "body": '{"transactionId":"tx-1","responseBody":{"memberIdWithPrefix":"LH001-12345","name":"Jane","dob":"1990-01-01"}}',
    }

    def mock_executor(req: dict) -> dict:
        return mock_response

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert "canonicalResponseEnvelope" in result
    assert result["canonicalResponseEnvelope"].get("memberIdWithPrefix") == "LH001-12345"
    assert result["canonicalResponseEnvelope"].get("name") == "Jane"


def test_execute_without_response_body_no_canonical_envelope() -> None:
    """When body has no responseBody, canonicalResponseEnvelope is not set."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }

    def mock_executor(req: dict) -> dict:
        return {"statusCode": 200, "body": '{"transactionId":"tx-1","status":"completed"}'}

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert "canonicalResponseEnvelope" not in result or result.get("canonicalResponseEnvelope") is None


def test_dry_run_includes_vendor_request_preview() -> None:
    """DRY_RUN includes mappingSummary and vendorRequestPreview for mapped vendor pair."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "DRY_RUN",
        "envelope": _eligibility_envelope(),
    }
    result = run_canonical_bridge(payload)
    assert result["mode"] == "DRY_RUN"
    assert result["valid"] is True
    assert "mappingSummary" in result
    assert result["mappingSummary"].get("available") is True
    assert "vendorRequestPreview" in result
    assert result["vendorRequestPreview"] == {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"}


def test_execute_with_response_body_sets_canonical_response_envelope() -> None:
    """When executor returns body with responseBody, bridge sets canonicalResponseEnvelope."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }
    canonical_resp = {"memberIdWithPrefix": "LH001-12345", "name": "Jane", "status": "eligible"}

    def mock_executor(req: dict) -> dict:
        return {
            "statusCode": 200,
            "body": '{"transactionId":"tx-1","responseBody":' + __import__("json").dumps(canonical_resp) + "}",
        }

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert "canonicalResponseEnvelope" in result
    assert result["canonicalResponseEnvelope"] == canonical_resp


def test_execute_without_response_body_no_canonical_envelope() -> None:
    """When body has no responseBody, canonicalResponseEnvelope is not set."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }

    def mock_executor(req: dict) -> dict:
        return {"statusCode": 200, "body": '{"transactionId":"tx-1","status":"completed"}'}

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert result.get("canonicalResponseEnvelope") is None


def test_dry_run_includes_vendor_request_preview() -> None:
    """DRY_RUN includes mappingSummary and vendorRequestPreview for mapped vendor pair."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "DRY_RUN",
        "envelope": _eligibility_envelope(),
    }
    result = run_canonical_bridge(payload)
    assert result["mode"] == "DRY_RUN"
    assert result["valid"] is True
    assert "mappingSummary" in result
    assert result["mappingSummary"]["available"] is True
    assert "vendorRequestPreview" in result
    assert result["vendorRequestPreview"] == {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"}


def test_execute_with_response_body_sets_canonical_response_envelope() -> None:
    """When executor returns body with responseBody, bridge sets canonicalResponseEnvelope."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }
    mock_body = {
        "transactionId": "tx-123",
        "correlationId": "corr-test",
        "status": "completed",
        "responseBody": {"memberIdWithPrefix": "LH001-12345", "name": "Jane", "status": "eligible"},
    }

    def mock_executor(req: dict) -> dict:
        return {"statusCode": 200, "body": __import__("json").dumps(mock_body)}

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert "canonicalResponseEnvelope" in result
    assert result["canonicalResponseEnvelope"] == mock_body["responseBody"]


def test_execute_without_response_body_no_canonical_envelope() -> None:
    """When body has no responseBody, canonicalResponseEnvelope is not set."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }

    def mock_executor(req: dict) -> dict:
        return {"statusCode": 200, "body": '{"transactionId":"tx-123","status":"completed"}'}

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert result.get("canonicalResponseEnvelope") is None


def test_dry_run_includes_vendor_request_preview() -> None:
    """DRY_RUN includes mappingSummary and vendorRequestPreview for mapped vendor pair."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "DRY_RUN",
        "envelope": _eligibility_envelope(),
    }
    result = run_canonical_bridge(payload)
    assert result["mode"] == "DRY_RUN"
    assert result["valid"] is True
    assert "mappingSummary" in result
    assert result["mappingSummary"].get("available") is True
    assert "vendorRequestPreview" in result
    assert result["vendorRequestPreview"] == {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"}


def test_execute_with_response_body_sets_canonical_response_envelope() -> None:
    """When executor returns body with responseBody, bridge sets canonicalResponseEnvelope."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }
    mock_body = {
        "transactionId": "tx-123",
        "correlationId": "corr-test",
        "status": "completed",
        "responseBody": {"memberIdWithPrefix": "LH001-12345", "name": "Jane", "status": "eligible"},
    }

    def mock_executor(req: dict) -> dict:
        return {"statusCode": 200, "body": mock_body}

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert "canonicalResponseEnvelope" in result
    assert result["canonicalResponseEnvelope"] == mock_body["responseBody"]


def test_execute_without_response_body_no_canonical_envelope() -> None:
    """When body has no responseBody, canonicalResponseEnvelope is not set."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }

    def mock_executor(req: dict) -> dict:
        return {"statusCode": 200, "body": {"transactionId": "tx-123", "status": "completed"}}

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert result.get("canonicalResponseEnvelope") is None


def test_dry_run_includes_mapped_vendor_request_preview() -> None:
    """DRY_RUN includes mappingSummary and vendorRequestPreview for LH001->LH002."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "DRY_RUN",
        "envelope": _eligibility_envelope(),
    }
    result = run_canonical_bridge(payload)
    assert result["mode"] == "DRY_RUN"
    assert result["valid"] is True
    assert "mappingSummary" in result
    assert result["mappingSummary"].get("available") is True
    assert "vendorRequestPreview" in result
    assert result["vendorRequestPreview"] == {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"}


def test_execute_with_response_body_sets_canonical_response_envelope() -> None:
    """When executor returns body with responseBody, bridge sets canonicalResponseEnvelope."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }
    exec_body = {
        "transactionId": "tx-123",
        "status": "completed",
        "responseBody": {"memberIdWithPrefix": "LH001-12345", "name": "Jane", "status": "eligible"},
    }

    def mock_executor(req: dict) -> dict:
        return {"statusCode": 200, "body": exec_body}

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert "canonicalResponseEnvelope" in result
    assert result["canonicalResponseEnvelope"] == exec_body["responseBody"]


def test_execute_without_response_body_no_canonical_envelope() -> None:
    """When body has no responseBody, canonicalResponseEnvelope is not set."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }

    def mock_executor(req: dict) -> dict:
        return {"statusCode": 200, "body": {"transactionId": "tx-123", "status": "completed"}}

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert "canonicalResponseEnvelope" not in result or result.get("canonicalResponseEnvelope") is None


def test_dry_run_includes_mapped_vendor_request_preview() -> None:
    """DRY_RUN includes mappingSummary and vendorRequestPreview for mapped vendor pair."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "DRY_RUN",
        "envelope": _eligibility_envelope(),
    }
    result = run_canonical_bridge(payload)
    assert result["mode"] == "DRY_RUN"
    assert result["valid"] is True
    assert "mappingSummary" in result
    assert result["mappingSummary"].get("available") is True
    assert "vendorRequestPreview" in result
    assert result["vendorRequestPreview"] == {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"}


def test_execute_with_response_body_sets_canonical_response_envelope() -> None:
    """When executor returns body with responseBody, bridge sets canonicalResponseEnvelope."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }
    mock_body = {
        "transactionId": "tx-123",
        "correlationId": "corr-test",
        "status": "completed",
        "responseBody": {"memberIdWithPrefix": "LH001-12345", "name": "Jane", "status": "eligible"},
    }

    def mock_executor(req: dict) -> dict:
        return {"statusCode": 200, "body": mock_body}

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert "canonicalResponseEnvelope" in result
    assert result["canonicalResponseEnvelope"] == mock_body["responseBody"]


def test_execute_without_response_body_no_canonical_envelope() -> None:
    """When body has no responseBody, canonicalResponseEnvelope is not set."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }

    def mock_executor(req: dict) -> dict:
        return {"statusCode": 200, "body": {"transactionId": "tx-123", "status": "completed"}}

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert result.get("canonicalResponseEnvelope") is None


def test_dry_run_includes_vendor_request_preview() -> None:
    """DRY_RUN includes mappingSummary and vendorRequestPreview when mapping exists."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "DRY_RUN",
        "envelope": _eligibility_envelope(),
    }
    result = run_canonical_bridge(payload)
    assert result["mode"] == "DRY_RUN"
    assert result["valid"] is True
    assert "mappingSummary" in result
    assert result["mappingSummary"].get("available") is True
    assert "vendorRequestPreview" in result
    assert result["vendorRequestPreview"] == {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"}


def test_execute_with_response_body_sets_canonical_response_envelope() -> None:
    """When execute returns responseBody, bridge sets canonicalResponseEnvelope."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }
    mock_body = {
        "transactionId": "tx-123",
        "correlationId": "corr-test",
        "status": "completed",
        "responseBody": {"memberIdWithPrefix": "LH001-12345", "name": "Jane", "status": "eligible"},
    }

    def mock_executor(req: dict) -> dict:
        return {"statusCode": 200, "body": mock_body}

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert "canonicalResponseEnvelope" in result
    assert result["canonicalResponseEnvelope"] == {"memberIdWithPrefix": "LH001-12345", "name": "Jane", "status": "eligible"}


def test_execute_without_response_body_no_canonical_envelope() -> None:
    """When execute body has no responseBody, canonicalResponseEnvelope is not set."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }

    def mock_executor(req: dict) -> dict:
        return {"statusCode": 200, "body": {"transactionId": "tx-123", "status": "completed"}}

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert result.get("canonicalResponseEnvelope") is None


def test_dry_run_includes_vendor_request_preview() -> None:
    """DRY_RUN includes mappingSummary and vendorRequestPreview when mapping exists."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "DRY_RUN",
        "envelope": _eligibility_envelope(),
    }
    result = run_canonical_bridge(payload)
    assert result["mode"] == "DRY_RUN"
    assert result["valid"] is True
    assert "mappingSummary" in result
    assert result["mappingSummary"].get("available") is True
    assert "vendorRequestPreview" in result
    assert result["vendorRequestPreview"] == {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"}


def test_execute_with_response_body_sets_canonical_response_envelope() -> None:
    """When execute returns responseBody, bridge sets canonicalResponseEnvelope."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }
    mock_body = {
        "transactionId": "tx-1",
        "correlationId": "corr-1",
        "status": "completed",
        "responseBody": {"memberIdWithPrefix": "LH001-12345", "name": "Jane", "status": "eligible"},
    }

    def mock_executor(req: dict) -> dict:
        return {"statusCode": 200, "body": mock_body}

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert "canonicalResponseEnvelope" in result
    assert result["canonicalResponseEnvelope"] == mock_body["responseBody"]


def test_execute_without_response_body_no_canonical_envelope() -> None:
    """When execute body has no responseBody, canonicalResponseEnvelope is not set."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }

    def mock_executor(req: dict) -> dict:
        return {"statusCode": 200, "body": {"transactionId": "tx-1", "status": "completed"}}

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert result.get("canonicalResponseEnvelope") is None


def test_dry_run_includes_mapped_vendor_request_preview() -> None:
    """DRY_RUN includes vendorRequestPreview when mapping exists for LH001->LH002."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "DRY_RUN",
        "envelope": _eligibility_envelope(),
    }
    result = run_canonical_bridge(payload)
    assert result["mode"] == "DRY_RUN"
    assert result["valid"] is True
    assert "vendorRequestPreview" in result
    assert result["vendorRequestPreview"] == {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"}
    assert "mappingSummary" in result
    assert result["mappingSummary"].get("available") is True


def test_execute_with_response_body_sets_canonical_response_envelope() -> None:
    """When execute returns responseBody, bridge sets canonicalResponseEnvelope."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }
    mock_body = {
        "transactionId": "tx-123",
        "correlationId": "corr-test",
        "status": "completed",
        "responseBody": {"memberIdWithPrefix": "LH001-12345", "name": "Jane", "status": "eligible"},
    }

    def mock_executor(req: dict) -> dict:
        return {"statusCode": 200, "body": mock_body}

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert "canonicalResponseEnvelope" in result
    assert result["canonicalResponseEnvelope"] == {"memberIdWithPrefix": "LH001-12345", "name": "Jane", "status": "eligible"}


def test_execute_without_response_body_no_canonical_envelope() -> None:
    """When execute returns body without responseBody, no canonicalResponseEnvelope."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }

    def mock_executor(req: dict) -> dict:
        return {"statusCode": 200, "body": {"transactionId": "tx-123", "error": "no payload"}}

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert result.get("canonicalResponseEnvelope") is None


def test_blocked_preflight_prevents_execution_no_runtime_duplication() -> None:
    """Blocked preflight prevents execution; executor is never called."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": {
            "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
            "version": "1.0",
            "direction": "REQUEST",
            "correlationId": "corr",
            "timestamp": "2025-03-06T12:00:00Z",
            "context": {},
            "payload": {},  # missing memberIdWithPrefix -> transform fails -> BLOCKED
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


def test_dry_run_includes_mapped_vendor_request_preview() -> None:
    """DRY_RUN includes mappingSummary and vendorRequestPreview when mapping exists."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "DRY_RUN",
        "envelope": _eligibility_envelope(),
    }
    result = run_canonical_bridge(payload)
    assert result["mode"] == "DRY_RUN"
    assert result["valid"] is True
    assert "mappingSummary" in result
    assert result["mappingSummary"].get("available") is True
    assert "vendorRequestPreview" in result
    assert result["vendorRequestPreview"] == {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"}


def test_execute_with_response_body_sets_canonical_response_envelope() -> None:
    """EXECUTE with responseBody in execute result sets canonicalResponseEnvelope."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }
    mock_body = {
        "transactionId": "tx-123",
        "correlationId": "corr-test",
        "status": "completed",
        "responseBody": {"memberIdWithPrefix": "LH001-12345", "name": "Jane", "status": "eligible"},
    }

    def mock_executor(req: dict) -> dict:
        return {"statusCode": 200, "body": mock_body}

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert "canonicalResponseEnvelope" in result
    assert result["canonicalResponseEnvelope"] == mock_body["responseBody"]


def test_execute_without_response_body_no_canonical_envelope() -> None:
    """EXECUTE with body lacking responseBody does not set canonicalResponseEnvelope."""
    payload = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mode": "EXECUTE",
        "envelope": _eligibility_envelope(),
    }

    def mock_executor(req: dict) -> dict:
        return {"statusCode": 200, "body": {"transactionId": "tx-123", "status": "completed"}}

    result = run_canonical_bridge(payload, executor=mock_executor)
    assert result["status"] == "EXECUTED"
    assert result.get("canonicalResponseEnvelope") is None
