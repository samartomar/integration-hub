"""AI Formatter helpers for AI gateway decisioning and rendering."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, TypedDict

# Limit prompt + JSON size to avoid abuse
_DEFAULT_PROMPT_MAX_CHARS = 4096
_DEFAULT_JSON_TRUNCATE_CHARS = 32000


class AiFormatterConfig(TypedDict, total=False):
    """Request-level AI formatter config (from request body aiFormatter object)."""

    mode: str  # "AUTO" | "FORCE_ON" | "FORCE_OFF"
    outputType: str  # "TEXT"
    promptOverride: str


class OperationAiConfig(TypedDict, total=False):
    """Operation-level AI config from control_plane.operations."""

    ai_presentation_mode: str | None  # "RAW_ONLY" | "RAW_AND_FORMATTED"
    ai_formatter_prompt: str | None
    ai_formatter_model: str | None


class AIFormatterReason:
    FEATURE_DISABLED = "FEATURE_DISABLED"
    MODE_RAW_ONLY = "MODE_RAW_ONLY"
    REQUEST_DISABLED = "REQUEST_DISABLED"
    FORMATTER_ERROR = "FORMATTER_ERROR"
    APPLIED = "APPLIED"
    PROMPT_MODE = "PROMPT_MODE"


@dataclass
class FormatterDecision:
    should_call: bool
    reason: str
    mode: str | None


_UNKNOWN_MODE_LOGGED: set[str] = set()


def normalize_operation_mode(raw_mode: str | None) -> str:
    """Normalize operation mode to RAW_ONLY or RAW_AND_FORMATTED."""
    mode = (raw_mode or "").strip().upper()
    if mode in ("RAW_ONLY", "RAW_AND_FORMATTED"):
        return mode
    if mode and mode not in _UNKNOWN_MODE_LOGGED:
        _UNKNOWN_MODE_LOGGED.add(mode)
    return "RAW_ONLY"


def decide_formatter_action(
    *,
    request_type: str,
    global_gate_enabled: bool,
    operation_mode: str | None,
    request_flag: bool | None,
) -> FormatterDecision:
    """
    Decision precedence:
      1) GLOBAL_GATE
      2) OP_MODE
      3) REQUEST_FLAG
      4) FORMATTER_CALL
    """
    rt = (request_type or "").strip().upper()
    if rt == "PROMPT":
        return FormatterDecision(False, AIFormatterReason.PROMPT_MODE, None)

    mode = normalize_operation_mode(operation_mode)
    if not global_gate_enabled:
        return FormatterDecision(False, AIFormatterReason.FEATURE_DISABLED, mode)
    if mode == "RAW_ONLY":
        return FormatterDecision(False, AIFormatterReason.MODE_RAW_ONLY, mode)
    if request_flag is not True:
        return FormatterDecision(False, AIFormatterReason.REQUEST_DISABLED, mode)
    return FormatterDecision(True, AIFormatterReason.APPLIED, mode)


_DEFAULT_SYSTEM_PROMPT = (
    "Given the following JSON response, produce a concise human-readable summary. "
    "Be brief, voice-friendly, and avoid emojis."
)


def build_formatter_prompt(
    op_cfg: OperationAiConfig,
    canonical_response: dict[str, Any],
    request_cfg: AiFormatterConfig | bool | None,
    json_max_chars: int = _DEFAULT_JSON_TRUNCATE_CHARS,
) -> str:
    """
    Build the formatter prompt from operation config and canonical response.

    - Base instruction from op_cfg.ai_formatter_prompt, or generic default.
    - Append pretty-printed canonical JSON (truncated if needed).
    - If request_cfg has promptOverride, append as "Additional instructions: ...".
    """
    base = (op_cfg.get("ai_formatter_prompt") or "").strip()
    if not base:
        base = _DEFAULT_SYSTEM_PROMPT

    json_str = json.dumps(canonical_response, indent=2)
    if len(json_str) > json_max_chars:
        json_str = json_str[: json_max_chars] + "\n... [truncated]"

    user_prompt = f"{base}\n\n```json\n{json_str}\n```"

    if isinstance(request_cfg, dict):
        override = (request_cfg.get("promptOverride") or "").strip()
        if override:
            user_prompt += f"\n\nAdditional instructions: {override}"

    return user_prompt


def build_local_stub_summary(raw_payload: Any, max_chars: int = 600) -> str:
    """Deterministic local formatter summary from JSON payload."""
    try:
        text = json.dumps(raw_payload, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        text = str(raw_payload)
    if len(text) > max_chars:
        text = text[:max_chars] + "...[truncated]"
    return f"AI formatted (local stub): {text}"


class FormatterError(Exception):
    """Raised when formatter call fails. Callers can distinguish from base call failure."""

    def __init__(self, message: str, model_id: str, cause: Exception | None = None):
        self.message = message
        self.model_id = model_id
        self.cause = cause
        super().__init__(message)


FormatterModelError = FormatterError  # Alias


def call_formatter_model(
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 512,
    region_name: str | None = None,
) -> str:
    """
    Invoke Bedrock model for single-shot completion. No tools, text-in -> text-out.

    Uses bedrock-runtime invoke_model with Anthropic Claude format.
    Raises FormatterError on failure so callers can handle without masking base success.
    In local mode (RUN_ENV=local or USE_BEDROCK=false): returns stub text.
    """
    run_env = (os.environ.get("RUN_ENV") or "").strip().lower()
    use_bedrock = (os.environ.get("USE_BEDROCK", "true")).strip().lower() not in ("false", "0")
    if run_env == "local" or not use_bedrock:
        return "(local stub) Formatted summary of the response."
    import boto3

    if not model_id or not str(model_id).strip():
        raise FormatterError("model_id is required", model_id or "")

    # Truncate prompts to avoid abuse
    prompt_max = int(os.environ.get("AI_FORMATTER_PROMPT_MAX_CHARS", _DEFAULT_PROMPT_MAX_CHARS))
    if len(system_prompt) > prompt_max:
        system_prompt = system_prompt[: prompt_max - 20] + "... [truncated]"
    if len(user_prompt) > prompt_max:
        user_prompt = user_prompt[: prompt_max - 20] + "... [truncated]"

    body: dict[str, Any] = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }

    safe_model_id = (model_id or "").strip()
    try:
        client = boto3.client("bedrock-runtime", region_name=region_name)
        response = client.invoke_model(
            modelId=safe_model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        raw = response.get("body")
        if raw is None:
            raise FormatterError("Empty Bedrock response", safe_model_id)
        parsed = json.loads(raw.read().decode())
        content = parsed.get("content") or []
        if not content:
            return ""
        text_block = content[0] if isinstance(content[0], dict) else {}
        return (text_block.get("text") or "").strip()
    except json.JSONDecodeError as e:
        raise FormatterError(f"Invalid Bedrock response JSON: {e}", safe_model_id, e) from e
    except Exception as e:
        if isinstance(e, FormatterError):
            raise
        raise FormatterError(f"Bedrock invocation failed: {e}", safe_model_id, e) from e
