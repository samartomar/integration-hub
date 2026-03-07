"""Unit tests for flow runtime handoff service."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "apps" / "api" / "src"))

from schema.flow_runtime_handoff import (
    build_flow_runtime_handoff,
    maybe_run_flow_handoff_preflight,
)


def _valid_draft() -> dict:
    return {
        "name": "Eligibility Check Flow",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "trigger": {"type": "MANUAL"},
        "mappingMode": "CANONICAL_FIRST",
        "notes": "optional",
    }


def _valid_payload() -> dict:
    return {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"}


def test_valid_draft_and_payload_builds_canonical_execution_package() -> None:
    """Valid draft + payload builds canonical execution package."""
    body = {"draft": _valid_draft(), "payload": _valid_payload(), "context": {}, "runPreflight": False}
    result = build_flow_runtime_handoff(body)
    assert result["valid"] is True
    assert result["flowName"] == "Eligibility Check Flow"
    assert result["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert result["canonicalVersion"] == "1.0"
    assert result["sourceVendor"] == "LH001"
    assert result["targetVendor"] == "LH002"
    assert result["triggerType"] == "MANUAL"
    assert result["mappingMode"] == "CANONICAL_FIRST"

    pkg = result.get("canonicalExecutionPackage")
    assert pkg is not None
    assert pkg["sourceVendor"] == "LH001"
    assert pkg["targetVendor"] == "LH002"
    envelope = pkg["envelope"]
    assert envelope["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert envelope["version"] == "1.0"
    assert envelope["direction"] == "REQUEST"
    assert envelope["payload"] == _valid_payload()
    assert "correlationId" in envelope
    assert "timestamp" in envelope

    assert "preflight" not in result
    notes = result.get("notes") or []
    assert any("No runtime execution performed" in n for n in notes)


def test_alias_version_v1_normalizes_to_1_0() -> None:
    """Alias version v1 normalizes to 1.0."""
    draft = dict(_valid_draft())
    draft["version"] = "v1"
    body = {"draft": draft, "payload": _valid_payload(), "runPreflight": False}
    result = build_flow_runtime_handoff(body)
    assert result["valid"] is True
    assert result["canonicalVersion"] == "1.0"
    assert result["canonicalExecutionPackage"]["envelope"]["version"] == "1.0"


def test_absent_payload_falls_back_to_canonical_example_request() -> None:
    """Absent payload falls back to canonical example request if available."""
    body = {"draft": _valid_draft(), "context": {}, "runPreflight": False}
    result = build_flow_runtime_handoff(body)
    assert result["valid"] is True
    pkg = result["canonicalExecutionPackage"]
    payload = pkg["envelope"]["payload"]
    assert "memberIdWithPrefix" in payload
    assert "date" in payload


def test_invalid_draft_fails_clearly() -> None:
    """Invalid draft fails clearly."""
    body = {"draft": {"name": "X", "operationCode": "X"}, "runPreflight": False}
    result = build_flow_runtime_handoff(body)
    assert result["valid"] is False
    assert "errors" in result
    assert len(result["errors"]) >= 1
    assert "canonicalExecutionPackage" not in result or result["canonicalExecutionPackage"] is None


def test_unknown_operation_fails_clearly() -> None:
    """Unknown operation fails clearly."""
    draft = dict(_valid_draft())
    draft["operationCode"] = "UNKNOWN_OP_XYZ"
    draft["version"] = "1.0"
    body = {"draft": draft, "runPreflight": False}
    result = build_flow_runtime_handoff(body)
    assert result["valid"] is False
    assert "errors" in result
    assert "not found" in result["errors"][0].get("message", "").lower()


def test_run_preflight_true_attaches_preflight_result() -> None:
    """runPreflight=true attaches existing preflight result."""
    body = {"draft": _valid_draft(), "payload": _valid_payload(), "runPreflight": True}
    result = build_flow_runtime_handoff(body)
    assert result["valid"] is True
    assert "preflight" in result
    preflight = result["preflight"]
    assert "valid" in preflight
    assert "status" in preflight
    assert "checks" in preflight
    assert preflight["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert preflight["canonicalVersion"] == "1.0"


def test_handoff_never_executes_runtime() -> None:
    """Handoff never executes runtime - no executeResult or similar."""
    body = {"draft": _valid_draft(), "payload": _valid_payload(), "runPreflight": True}
    result = build_flow_runtime_handoff(body)
    assert "executeResult" not in result
    assert "executionPlan" not in result or "EXECUTE" not in str(result.get("executionPlan", ""))


def test_missing_draft_returns_invalid() -> None:
    """Missing draft returns invalid."""
    result = build_flow_runtime_handoff({"runPreflight": False})
    assert result["valid"] is False
    assert any("draft" in str(e).lower() for e in result.get("errors", []))


def test_maybe_run_flow_handoff_preflight_attaches_preflight() -> None:
    """maybe_run_flow_handoff_preflight attaches preflight to existing handoff."""
    body = {"draft": _valid_draft(), "payload": _valid_payload(), "runPreflight": False}
    handoff = build_flow_runtime_handoff(body)
    assert "preflight" not in handoff

    out = maybe_run_flow_handoff_preflight(handoff)
    assert "preflight" in out
    assert out["preflight"]["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert handoff is not out
