"""Tests for bedrock_debugger_enricher - PHI-safe, fallback behavior."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "apps" / "api" / "src"))

from ai.bedrock_debugger_enricher import (
    build_redacted_debugger_prompt,
    enrich_debug_report_with_bedrock,
    maybe_should_use_bedrock,
)


def test_build_redacted_prompt_excludes_payload_bodies() -> None:
    """Redacted prompt must not include normalizedArtifacts payload/draft/sandboxResult."""
    report = {
        "debugType": "CANONICAL_REQUEST",
        "status": "FAIL",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "summary": "Validation failed",
        "findings": [{"severity": "ERROR", "code": "INVALID_DATE", "message": "Field payload.date", "field": "payload.date", "suggestion": "Use YYYY-MM-DD"}],
        "normalizedArtifacts": {
            "payload": {"memberIdWithPrefix": "LH001-12345", "date": "invalid", "ssn": "123-45-6789"},
        },
        "notes": ["Deterministic only"],
    }
    prompt = build_redacted_debugger_prompt(report)
    assert "memberIdWithPrefix" not in prompt
    assert "123-45-6789" not in prompt
    assert "payload" not in prompt or "payload.date" in prompt  # field name ok
    assert "debugType" in prompt
    assert "CANONICAL_REQUEST" in prompt
    assert "status" in prompt
    assert "FAIL" in prompt
    assert "findings" in prompt


def test_build_redacted_prompt_sanitizes_finding_messages() -> None:
    """Finding messages with quoted values should be sanitized."""
    report = {
        "debugType": "CANONICAL_REQUEST",
        "status": "FAIL",
        "operationCode": "X",
        "version": "1.0",
        "summary": "Fail",
        "findings": [{"severity": "ERROR", "code": "X", "message": "Field payload: '123-45-6789' is invalid", "field": "payload", "suggestion": None}],
        "normalizedArtifacts": {},
        "notes": [],
    }
    prompt = build_redacted_debugger_prompt(report)
    assert "123-45-6789" not in prompt
    assert "[REDACTED]" in prompt


def test_maybe_should_use_bedrock_disabled_by_default() -> None:
    """When enhanceWithAi not true, returns False."""
    assert maybe_should_use_bedrock(False, {}) is False
    assert maybe_should_use_bedrock({}, {}) is False
    assert maybe_should_use_bedrock({"enhanceWithAi": False}, {}) is False


def test_maybe_should_use_bedrock_requires_enabled_and_model() -> None:
    """Requires BEDROCK_DEBUGGER_ENABLED and BEDROCK_DEBUGGER_MODEL_ID."""
    cfg = {"BEDROCK_DEBUGGER_ENABLED": "true", "BEDROCK_DEBUGGER_MODEL_ID": "anthropic.claude-3-haiku"}
    assert maybe_should_use_bedrock(True, cfg) is True
    cfg_disabled = {"BEDROCK_DEBUGGER_ENABLED": "false", "BEDROCK_DEBUGGER_MODEL_ID": "x"}
    assert maybe_should_use_bedrock(True, cfg_disabled) is False
    cfg_no_model = {"BEDROCK_DEBUGGER_ENABLED": "true", "BEDROCK_DEBUGGER_MODEL_ID": ""}
    assert maybe_should_use_bedrock(True, cfg_no_model) is False


@patch.dict("os.environ", {"BEDROCK_DEBUGGER_ENABLED": "false"}, clear=False)
def test_enrich_returns_fallback_when_disabled() -> None:
    """When disabled, returns fallback with enhanced=false."""
    report = {"debugType": "CANONICAL_REQUEST", "status": "PASS", "summary": "OK", "findings": [], "notes": []}
    result = enrich_debug_report_with_bedrock(report)
    assert result["modelInfo"]["enhanced"] is False
    assert "aiWarnings" in result
    assert "AI enhancement unavailable" in str(result["aiWarnings"])


@patch.dict("os.environ", {"BEDROCK_DEBUGGER_ENABLED": "true", "BEDROCK_DEBUGGER_MODEL_ID": ""}, clear=False)
def test_enrich_returns_fallback_when_no_model() -> None:
    """When model ID missing, returns fallback."""
    report = {"debugType": "CANONICAL_REQUEST", "status": "PASS", "summary": "OK", "findings": [], "notes": []}
    result = enrich_debug_report_with_bedrock(report)
    assert result["modelInfo"]["enhanced"] is False


@patch("ai.bedrock_debugger_enricher.invoke_debugger_model")
@patch.dict("os.environ", {"BEDROCK_DEBUGGER_ENABLED": "true", "BEDROCK_DEBUGGER_MODEL_ID": "anthropic.claude-3-haiku", "RUN_ENV": "prod"}, clear=False)
def test_enrich_success_returns_structured_output(mock_invoke: object) -> None:
    """Successful Bedrock call returns aiSummary, remediationPlan, modelInfo."""
    mock_invoke.return_value = '{"aiSummary": "Fix the date.", "remediationPlan": [{"priority": 1, "title": "Fix date", "reason": "Invalid format", "action": "Use YYYY-MM-DD"}], "prioritizedNextSteps": ["Fix date"], "aiWarnings": ["Advisory only"]}'
    report = {"debugType": "CANONICAL_REQUEST", "status": "FAIL", "summary": "Fail", "findings": [], "notes": []}
    result = enrich_debug_report_with_bedrock(report)
    assert result["modelInfo"]["enhanced"] is True
    assert result["aiSummary"] == "Fix the date."
    assert len(result.get("remediationPlan", [])) == 1
    assert result["remediationPlan"][0]["title"] == "Fix date"


@patch("ai.bedrock_debugger_enricher.invoke_debugger_model")
@patch.dict("os.environ", {"BEDROCK_DEBUGGER_ENABLED": "true", "BEDROCK_DEBUGGER_MODEL_ID": "x", "RUN_ENV": "prod"}, clear=False)
def test_enrich_bedrock_error_returns_fallback(mock_invoke: object) -> None:
    """Bedrock error returns fallback, deterministic report preserved by caller."""
    mock_invoke.side_effect = Exception("Bedrock timeout")
    report = {"debugType": "CANONICAL_REQUEST", "status": "PASS", "summary": "OK", "findings": [], "notes": []}
    result = enrich_debug_report_with_bedrock(report)
    assert result["modelInfo"]["enhanced"] is False
    assert "aiWarnings" in result
    assert "AI enhancement unavailable" in str(result["aiWarnings"])


@patch("ai.bedrock_debugger_enricher.invoke_debugger_model")
@patch.dict("os.environ", {"BEDROCK_DEBUGGER_ENABLED": "true", "BEDROCK_DEBUGGER_MODEL_ID": "x", "RUN_ENV": "prod"}, clear=False)
def test_enrich_malformed_response_returns_fallback(mock_invoke: object) -> None:
    """Malformed JSON from model returns fallback."""
    mock_invoke.return_value = "not valid json {{{"
    report = {"debugType": "CANONICAL_REQUEST", "status": "PASS", "summary": "OK", "findings": [], "notes": []}
    result = enrich_debug_report_with_bedrock(report)
    assert result["modelInfo"]["enhanced"] is False
