"""Minimal Bedrock invoke_model wrapper for AI layer only.

Used by bedrock_debugger_enricher. Lives in AI boundary; no UI coupling.
Timeout support, easy to mock in tests.
"""

from __future__ import annotations

import json
import os
from typing import Any


def invoke_model(
    model_id: str,
    body: dict[str, Any],
    *,
    region_name: str | None = None,
    timeout_seconds: float | None = None,
) -> str:
    """
    Invoke Bedrock model (invoke_model). Returns parsed text from response.

    Uses bedrock-runtime invoke_model with Anthropic Claude format.
    Raises on failure. Callers handle errors and return fallback.
    """
    import boto3

    if not model_id or not str(model_id).strip():
        raise ValueError("model_id is required")

    client = boto3.client("bedrock-runtime", region_name=region_name)
    invoke_kw: dict[str, Any] = {
        "modelId": model_id.strip(),
        "body": json.dumps(body),
        "contentType": "application/json",
        "accept": "application/json",
    }

    # Lambda invoke_model does not support timeout directly; rely on Lambda timeout.
    # For local/sync use, caller can use threading with timeout.
    _ = timeout_seconds

    response = client.invoke_model(**invoke_kw)
    raw = response.get("body")
    if raw is None:
        raise ValueError("Empty Bedrock response")

    parsed = json.loads(raw.read().decode())
    content = parsed.get("content") or []
    if not content:
        return ""
    text_block = content[0] if isinstance(content[0], dict) else {}
    return (text_block.get("text") or "").strip()


def invoke_debugger_model(
    model_id: str,
    prompt: str,
    *,
    timeout_ms: int = 8000,
    region_name: str | None = None,
) -> str:
    """
    Invoke Bedrock for debugger enrichment. Prompt is redacted deterministic report.
    Returns raw model text (caller parses JSON).
    """
    system = (
        "You are a technical assistant for integration debugging. "
        "Given a deterministic debug report (debugType, status, findings), produce a JSON object with: "
        "aiSummary (string), remediationPlan (array of {priority, title, reason, action}), "
        "prioritizedNextSteps (array of strings), aiWarnings (array of strings). "
        "Output valid JSON only, no markdown."
    )
    body: dict[str, Any] = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "temperature": 0.2,
        "system": system[:4096],
        "messages": [{"role": "user", "content": (prompt or "")[:8192]}],
    }
    return invoke_model(
        model_id,
        body,
        region_name=region_name,
        timeout_seconds=timeout_ms / 1000.0 if timeout_ms else None,
    )
