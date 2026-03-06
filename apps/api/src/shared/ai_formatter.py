"""Shared AI Formatter helper for Central AI Endpoint and optional AI Tool Lambda integration.

Provides:
- should_apply_formatter: decide if formatter should run based on op config + request config
- build_formatter_prompt: build prompt from canonical response + op prompt
- call_formatter_model: invoke Bedrock model for text completion

Formatter failures must not mask successful Integration Hub responses.
"""

from __future__ import annotations

import json
import os
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


def _is_raw_only(mode: str | None) -> bool:
    """True if mode is RAW_ONLY."""
    if not mode or not isinstance(mode, str):
        return False
    return str(mode).strip().upper() == "RAW_ONLY"


def _is_formatter_capable(mode: str | None) -> bool:
    """True if operation supports formatter (RAW_AND_FORMATTED only)."""
    if not mode or not isinstance(mode, str):
        return False
    return str(mode).strip().upper() in ("RAW_AND_FORMATTED", "CANONICAL_TO_TEXT")


def should_apply_formatter(
    op_cfg: OperationAiConfig,
    request_cfg: AiFormatterConfig | bool | None,
    channel: str | None = None,
) -> bool:
    """
    Decide whether to apply the AI formatter.

    RAW_ONLY is a hard safety setting; even FORCE_ON cannot override it.
    Operation config wins over per-request flags for RAW_ONLY.

    - If op_cfg.ai_presentation_mode == "RAW_ONLY" -> always False.
    - Otherwise, if request_cfg is None: True when ai_presentation_mode is formatter-capable.
    - If request_cfg is bool: False when False; otherwise follow operation config (RAW_ONLY already handled).
    - If request_cfg is object:
      - "FORCE_OFF" -> False
      - "FORCE_ON" -> True (except RAW_ONLY -> False, handled above)
      - "AUTO" -> ai_presentation_mode != "RAW_ONLY"

    channel is reserved for future channel-specific behavior.
    """
    mode = (op_cfg.get("ai_presentation_mode") or "").strip() or None

    # RAW_ONLY overrides everything - operation config wins over request-level flags
    if _is_raw_only(mode):
        return False

    if isinstance(request_cfg, dict):
        cfg = request_cfg
        req_mode = (cfg.get("mode") or "").strip().upper()
        if req_mode == "FORCE_OFF":
            return False
        if req_mode == "FORCE_ON":
            return True
        if req_mode == "AUTO":
            return _is_formatter_capable(mode)
        return _is_formatter_capable(mode)

    if request_cfg is None:
        return _is_formatter_capable(mode)

    if isinstance(request_cfg, bool):
        return request_cfg and _is_formatter_capable(mode)

    return _is_formatter_capable(mode)


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


class FormatterError(Exception):
    """Raised when formatter call fails. Callers can distinguish from base call failure."""

    def __init__(self, message: str, model_id: str, cause: Exception | None = None):
        self.message = message
        self.model_id = model_id
        self.cause = cause
        super().__init__(message)


# Alias for compatibility with ai_gateway_lambda
FormatterModelError = FormatterError


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
    """
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

    try:
        client = boto3.client("bedrock-runtime", region_name=region_name)
        response = client.invoke_model(
            modelId=model_id.strip(),
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        raw = response.get("body")
        if raw is None:
            raise FormatterError("Empty Bedrock response", model_id)
        parsed = json.loads(raw.read().decode())
        content = parsed.get("content") or []
        if not content:
            return ""
        text_block = content[0] if isinstance(content[0], dict) else {}
        return (text_block.get("text") or "").strip()
    except json.JSONDecodeError as e:
        raise FormatterError(f"Invalid Bedrock response JSON: {e}", model_id, e) from e
    except Exception as e:
        if isinstance(e, FormatterError):
            raise
        raise FormatterError(f"Bedrock invocation failed: {e}", model_id, e) from e
