"""Unit tests for backend/shared ai_formatter helper."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add apps/api/src/lambda to path for ai_formatter (bundled there)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from ai_formatter import (
    AIFormatterReason,
    OperationAiConfig,
    build_formatter_prompt,
    decide_formatter_action,
    call_formatter_model,
    normalize_operation_mode,
)


def test_decide_formatter_action_gate_disabled() -> None:
    d = decide_formatter_action(
        request_type="DATA",
        global_gate_enabled=False,
        operation_mode="RAW_AND_FORMATTED",
        request_flag=True,
    )
    assert d.should_call is False
    assert d.reason == AIFormatterReason.FEATURE_DISABLED
    assert d.mode == "RAW_AND_FORMATTED"


def test_decide_formatter_action_raw_only() -> None:
    d = decide_formatter_action(
        request_type="DATA",
        global_gate_enabled=True,
        operation_mode="RAW_ONLY",
        request_flag=True,
    )
    assert d.should_call is False
    assert d.reason == AIFormatterReason.MODE_RAW_ONLY
    assert d.mode == "RAW_ONLY"


def test_decide_formatter_action_request_disabled() -> None:
    d = decide_formatter_action(
        request_type="DATA",
        global_gate_enabled=True,
        operation_mode="RAW_AND_FORMATTED",
        request_flag=False,
    )
    assert d.should_call is False
    assert d.reason == AIFormatterReason.REQUEST_DISABLED
    assert d.mode == "RAW_AND_FORMATTED"


def test_decide_formatter_action_applied() -> None:
    d = decide_formatter_action(
        request_type="DATA",
        global_gate_enabled=True,
        operation_mode="RAW_AND_FORMATTED",
        request_flag=True,
    )
    assert d.should_call is True
    assert d.reason == AIFormatterReason.APPLIED
    assert d.mode == "RAW_AND_FORMATTED"


def test_decide_formatter_action_prompt() -> None:
    d = decide_formatter_action(
        request_type="PROMPT",
        global_gate_enabled=False,
        operation_mode="RAW_ONLY",
        request_flag=False,
    )
    assert d.should_call is False
    assert d.reason == AIFormatterReason.PROMPT_MODE
    assert d.mode is None


def test_normalize_operation_mode_unknown_maps_to_raw_only() -> None:
    assert normalize_operation_mode("LEGACY_MODE") == "RAW_ONLY"


def test_build_formatter_prompt_includes_json() -> None:
    """build_formatter_prompt includes canonical JSON."""
    op_cfg: OperationAiConfig = {}
    canonical = {"status": "ok", "value": 42}
    prompt = build_formatter_prompt(op_cfg, canonical, None)
    assert "status" in prompt
    assert "ok" in prompt
    assert "value" in prompt
    assert "42" in prompt


def test_build_formatter_prompt_uses_ai_formatter_prompt() -> None:
    """build_formatter_prompt uses ai_formatter_prompt when provided."""
    op_cfg: OperationAiConfig = {"ai_formatter_prompt": "Summarize this for voice."}
    canonical = {"foo": "bar"}
    prompt = build_formatter_prompt(op_cfg, canonical, None)
    assert "Summarize this for voice" in prompt
    assert "foo" in prompt


def test_build_formatter_prompt_appends_prompt_override() -> None:
    """build_formatter_prompt appends promptOverride when present."""
    op_cfg: OperationAiConfig = {}
    canonical = {"x": 1}
    request_cfg = {"promptOverride": "Keep it under 50 chars."}
    prompt = build_formatter_prompt(op_cfg, canonical, request_cfg)
    assert "Additional instructions" in prompt or "Keep it under 50 chars" in prompt


@patch("boto3.client")
def test_call_formatter_model_mock(mock_boto_client: object) -> None:
    """call_formatter_model returns mock text (unit test, no real Bedrock)."""
    from io import BytesIO

    mock_client = mock_boto_client.return_value
    mock_client.invoke_model.return_value = {
        "body": BytesIO(b'{"content":[{"type":"text","text":"Current weather: 72F, sunny."}]}'),
    }
    result = call_formatter_model(
        "anthropic.claude-3-haiku-20240307-v1:0",
        "You are a formatter.",
        "Format this: {}",
    )
    assert "72F" in result or "sunny" in result
