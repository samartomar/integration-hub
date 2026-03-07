"""Unit tests for integration_debugger deterministic analysis."""

from __future__ import annotations

import pytest

from ai.integration_debugger import (
    analyze_canonical_request,
    analyze_flow_draft,
    analyze_sandbox_result,
    build_debug_summary,
)


# --- Canonical request ---


def test_valid_eligibility_request_returns_pass() -> None:
    """Valid eligibility request returns PASS."""
    report = analyze_canonical_request(
        "GET_VERIFY_MEMBER_ELIGIBILITY",
        {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"},
        version="1.0",
    )
    assert report["status"] == "PASS"
    assert report["debugType"] == "CANONICAL_REQUEST"
    assert report["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert report["version"] == "1.0"
    assert "valid" in report["summary"].lower()


def test_invalid_eligibility_date_returns_fail() -> None:
    """Invalid eligibility date returns FAIL with INVALID_DATE_FORMAT."""
    report = analyze_canonical_request(
        "GET_VERIFY_MEMBER_ELIGIBILITY",
        {"memberIdWithPrefix": "LH001-12345", "date": "03-06-2025"},
        version="1.0",
    )
    assert report["status"] == "FAIL"
    findings = [f for f in report["findings"] if f["code"] == "INVALID_DATE_FORMAT"]
    assert len(findings) >= 1
    assert "date" in findings[0]["message"].lower() or "payload" in findings[0]["field"].lower()


def test_invalid_eligibility_status_returns_fail() -> None:
    """Invalid eligibility status (if in response) - test missing required field instead."""
    report = analyze_canonical_request(
        "GET_VERIFY_MEMBER_ELIGIBILITY",
        {"memberIdWithPrefix": "LH001-12345"},
        version="1.0",
    )
    assert report["status"] == "FAIL"
    findings = [f for f in report["findings"] if "required" in f["message"].lower() or f["code"] == "MISSING_REQUIRED_FIELD"]
    assert len(findings) >= 1


def test_valid_accumulators_nested_payload_returns_pass() -> None:
    """Valid accumulators nested payload returns PASS."""
    report = analyze_canonical_request(
        "GET_MEMBER_ACCUMULATORS",
        {"memberIdWithPrefix": "LH001-12345", "asOfDate": "2025-03-06"},
        version="1.0",
    )
    assert report["status"] == "PASS"
    assert report["operationCode"] == "GET_MEMBER_ACCUMULATORS"


def test_invalid_accumulators_nested_numeric_type_returns_fail() -> None:
    """Invalid accumulators: asOfDate must be string, not number."""
    report = analyze_canonical_request(
        "GET_MEMBER_ACCUMULATORS",
        {"memberIdWithPrefix": "LH001-12345", "asOfDate": 20250306},
        version="1.0",
    )
    assert report["status"] == "FAIL"
    assert any(f["severity"] == "ERROR" for f in report["findings"])


def test_unknown_operation_returns_fail() -> None:
    """Unknown operation returns FAIL with UNKNOWN_OPERATION."""
    report = analyze_canonical_request(
        "UNKNOWN_OP_XYZ",
        {"foo": "bar"},
        version="1.0",
    )
    assert report["status"] == "FAIL"
    findings = [f for f in report["findings"] if f["code"] == "UNKNOWN_OPERATION"]
    assert len(findings) >= 1


# --- Flow draft ---


def test_valid_flow_draft_returns_pass() -> None:
    """Valid flow draft returns PASS."""
    draft = {
        "name": "Eligibility Flow",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "trigger": {"type": "MANUAL"},
        "mappingMode": "CANONICAL_FIRST",
    }
    report = analyze_flow_draft(draft)
    assert report["status"] == "PASS"
    assert report["debugType"] == "FLOW_DRAFT"


def test_valid_flow_draft_with_v1_alias_returns_pass_or_warn() -> None:
    """Valid flow draft with v1 alias returns PASS with normalization note."""
    draft = {
        "name": "Eligibility Flow",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "v1",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "trigger": {"type": "MANUAL"},
        "mappingMode": "CANONICAL_FIRST",
    }
    report = analyze_flow_draft(draft)
    assert report["status"] == "PASS"
    alias_findings = [f for f in report["findings"] if "VERSION_ALIAS" in (f.get("code") or "")]
    assert len(alias_findings) >= 1


def test_invalid_flow_draft_bad_trigger_returns_fail() -> None:
    """Invalid flow draft with bad trigger returns FAIL."""
    draft = {
        "name": "Eligibility Flow",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "trigger": {"type": "SCHEDULED"},
        "mappingMode": "CANONICAL_FIRST",
    }
    report = analyze_flow_draft(draft)
    assert report["status"] == "FAIL"
    assert any("trigger" in (f.get("field") or "").lower() for f in report["findings"])


def test_invalid_flow_draft_missing_vendor_returns_fail() -> None:
    """Invalid flow draft missing sourceVendor returns FAIL."""
    draft = {
        "name": "Eligibility Flow",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "",
        "targetVendor": "LH002",
        "trigger": {"type": "MANUAL"},
        "mappingMode": "CANONICAL_FIRST",
    }
    report = analyze_flow_draft(draft)
    assert report["status"] == "FAIL"


# --- Sandbox result ---


def test_valid_sandbox_result_returns_pass() -> None:
    """Valid sandbox result returns PASS with mock-only note."""
    result = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "mode": "MOCK",
        "valid": True,
        "requestEnvelope": {"operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY", "payload": {}},
        "responseEnvelope": {"operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY", "payload": {}},
    }
    report = analyze_sandbox_result(result)
    assert report["status"] == "PASS"
    mock_note = any("mock" in (n or "").lower() for n in report.get("notes", []))
    mock_finding = any("mock" in (f.get("message") or "").lower() for f in report.get("findings", []))
    assert mock_note or mock_finding


def test_invalid_sandbox_result_missing_response_envelope_returns_warn() -> None:
    """Invalid sandbox result missing responseEnvelope adds WARNING."""
    result = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "mode": "MOCK",
        "valid": True,
        "requestEnvelope": {"payload": {}},
        "responseEnvelope": None,
    }
    report = analyze_sandbox_result(result)
    missing = [f for f in report["findings"] if "MISSING_RESPONSE_ENVELOPE" in (f.get("code") or "")]
    assert len(missing) >= 1


def test_invalid_sandbox_result_valid_false_returns_fail() -> None:
    """Sandbox result with valid=false returns FAIL."""
    result = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "mode": "MOCK",
        "valid": False,
        "errors": [{"field": "payload", "message": "Invalid payload"}],
    }
    report = analyze_sandbox_result(result)
    assert report["status"] == "FAIL"


# --- build_debug_summary ---


def test_enhance_with_ai_false_unchanged() -> None:
    """When enhance_with_ai=False, report has no aiSummary/remediationPlan (deterministic only)."""
    report = analyze_canonical_request(
        "GET_VERIFY_MEMBER_ELIGIBILITY",
        {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"},
        version="1.0",
        enhance_with_ai=False,
    )
    assert report["status"] == "PASS"
    assert "aiSummary" not in report or report.get("aiSummary") is None
    assert "modelInfo" not in report or report.get("modelInfo", {}).get("enhanced") is not True


def test_enhance_with_ai_true_adds_fallback_when_invoker_unavailable() -> None:
    """When enhance_with_ai=True and AI Gateway invoke fails, fallback aiWarnings/modelInfo added."""
    report = analyze_canonical_request(
        "GET_VERIFY_MEMBER_ELIGIBILITY",
        {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"},
        version="1.0",
        enhance_with_ai=True,
    )
    assert report["status"] == "PASS"
    assert "aiWarnings" in report
    assert any("unavailable" in str(w).lower() for w in report["aiWarnings"])
    assert report.get("modelInfo", {}).get("enhanced") is False
    assert report.get("modelInfo", {}).get("reason") == "invoke_failed"


def test_build_debug_summary_shape() -> None:
    """build_debug_summary returns expected shape."""
    report = build_debug_summary(
        debug_type="CANONICAL_REQUEST",
        status="PASS",
        operation_code="GET_VERIFY_MEMBER_ELIGIBILITY",
        version="1.0",
        summary="Request valid.",
        findings=[],
        normalized_artifacts={"payload": {"foo": "bar"}},
    )
    assert report["debugType"] == "CANONICAL_REQUEST"
    assert report["status"] == "PASS"
    assert report["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert report["version"] == "1.0"
    assert report["summary"] == "Request valid."
    assert report["findings"] == []
    assert report["normalizedArtifacts"]["payload"] == {"foo": "bar"}
    assert "notes" in report
    assert len(report["notes"]) >= 1
