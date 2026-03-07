"""Bedrock debugger enricher - runs INSIDE AI Gateway Lambda only.

Takes deterministic debugger report, builds redacted prompt, calls Bedrock,
returns structured enrichment. Never mutates or replaces deterministic findings.
PHI-safe: no raw payload bodies, sanitized finding messages.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from ai.bedrock_client import invoke_debugger_model

# Keys that may contain user-provided values; replace with placeholder in messages
_SENSITIVE_PATTERNS = (
    r"'[^']*'",  # quoted strings
    r'"[^"]*"',  # double-quoted strings
    r"\d{3}-\d{2}-\d{4}",  # SSN-like
    r"[A-Z]{2}\d{3}-\d+",  # memberIdWithPrefix-like
)


def _sanitize_message(msg: str) -> str:
    """Replace literal user values in finding messages with placeholders."""
    if not msg or not isinstance(msg, str):
        return str(msg) if msg is not None else ""
    out = msg
    for pat in _SENSITIVE_PATTERNS:
        out = re.sub(pat, "[REDACTED]", out)
    return out


def _sanitize_finding(f: dict[str, Any]) -> dict[str, Any]:
    """Return safe finding: code, field, suggestion, severity; sanitized message."""
    return {
        "severity": f.get("severity", "INFO"),
        "code": f.get("code", "UNKNOWN"),
        "title": f.get("title", ""),
        "message": _sanitize_message(str(f.get("message", ""))),
        "field": f.get("field"),
        "suggestion": f.get("suggestion"),
    }


def build_redacted_debugger_prompt(report: dict[str, Any]) -> str:
    """
    Build PHI-safe prompt from deterministic report.

    Includes: debugType, status, summary, sanitized findings, operationCode, version.
    Excludes: normalizedArtifacts (payload, draft, sandboxResult bodies).
    """
    debug_type = report.get("debugType", "UNKNOWN")
    status = report.get("status", "UNKNOWN")
    summary = report.get("summary", "")
    operation_code = report.get("operationCode", "")
    version = report.get("version", "")
    findings_raw = report.get("findings") or []
    notes = report.get("notes") or []

    findings_safe = [_sanitize_finding(f) for f in findings_raw if isinstance(f, dict)]

    safe_report = {
        "debugType": debug_type,
        "status": status,
        "operationCode": operation_code,
        "version": version,
        "summary": summary,
        "findings": findings_safe,
        "notes": notes,
    }

    return json.dumps(safe_report, indent=2)


def maybe_should_use_bedrock(
    request_payload_or_flag: dict[str, Any] | bool | None,
    env_config: dict[str, str] | None = None,
) -> bool:
    """
    Decide whether to use Bedrock for debugger enrichment.

    - BEDROCK_DEBUGGER_ENABLED must be truthy
    - BEDROCK_DEBUGGER_MODEL_ID must be set
    - In local/dev, skip unless BEDROCK_DEBUGGER_ALLOW_LOCAL is set
    - Request must have enhanceWithAi=true (or equivalent)
    """
    cfg = env_config or {}
    enabled = (cfg.get("BEDROCK_DEBUGGER_ENABLED") or os.environ.get("BEDROCK_DEBUGGER_ENABLED", "")).strip().lower() in ("true", "1", "yes")
    model_id = (cfg.get("BEDROCK_DEBUGGER_MODEL_ID") or os.environ.get("BEDROCK_DEBUGGER_MODEL_ID", "")).strip()
    run_env = (cfg.get("RUN_ENV") or os.environ.get("RUN_ENV", "")).strip().lower()
    allow_local = (cfg.get("BEDROCK_DEBUGGER_ALLOW_LOCAL") or os.environ.get("BEDROCK_DEBUGGER_ALLOW_LOCAL", "")).strip().lower() in ("true", "1", "yes")

    if not enabled or not model_id:
        return False
    if run_env == "local" and not allow_local:
        return False

    if isinstance(request_payload_or_flag, bool):
        return request_payload_or_flag
    if isinstance(request_payload_or_flag, dict):
        return request_payload_or_flag.get("enhanceWithAi") is True
    return False


def enrich_debug_report_with_bedrock(
    report: dict[str, Any],
    mode: str | None = None,
) -> dict[str, Any]:
    """
    Enrich deterministic report with Bedrock-generated aiSummary, remediationPlan, etc.

    Runs only inside AI Gateway Lambda. Returns additive enrichment object.
    On failure: returns fallback with aiWarnings and modelInfo.enhanced=false.
    """
    enabled = (os.environ.get("BEDROCK_DEBUGGER_ENABLED", "")).strip().lower() in ("true", "1", "yes")
    model_id = (os.environ.get("BEDROCK_DEBUGGER_MODEL_ID", "")).strip()
    run_env = (os.environ.get("RUN_ENV", "")).strip().lower()
    allow_local = (os.environ.get("BEDROCK_DEBUGGER_ALLOW_LOCAL", "")).strip().lower() in ("true", "1", "yes")

    if not enabled or not model_id:
        return _fallback_enrichment("disabled_or_unavailable")
    if run_env == "local" and not allow_local:
        return _fallback_enrichment("local_skip")

    prompt = build_redacted_debugger_prompt(report)
    timeout_ms = int(os.environ.get("BEDROCK_DEBUGGER_TIMEOUT_MS", "8000"))

    try:
        raw = invoke_debugger_model(
            model_id=model_id,
            prompt=prompt,
            timeout_ms=timeout_ms,
        )
    except Exception as e:
        return _fallback_enrichment("bedrock_error", str(e)[:200])

    return _parse_enrichment_response(raw, model_id)


def _fallback_enrichment(reason: str, detail: str | None = None) -> dict[str, Any]:
    """Return fallback when Bedrock is unavailable."""
    warnings = ["AI enhancement unavailable; deterministic debugger result returned."]
    if detail:
        warnings.append(detail[:200])
    return {
        "aiWarnings": warnings,
        "modelInfo": {
            "provider": "bedrock",
            "enhanced": False,
            "reason": reason,
        },
    }


def _parse_enrichment_response(raw: str, model_id: str) -> dict[str, Any]:
    """Parse model output into enrichment contract. Handles malformed JSON safely."""
    raw = (raw or "").strip()
    if not raw:
        return _fallback_enrichment("empty_response")

    # Try to extract JSON block if model wrapped it in markdown
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    if json_match:
        raw = json_match.group(1).strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return _fallback_enrichment("malformed_response")

    if not isinstance(parsed, dict):
        return _fallback_enrichment("malformed_response")

    out: dict[str, Any] = {
        "aiSummary": (parsed.get("aiSummary") or "").strip() or None,
        "remediationPlan": parsed.get("remediationPlan") if isinstance(parsed.get("remediationPlan"), list) else [],
        "prioritizedNextSteps": parsed.get("prioritizedNextSteps") if isinstance(parsed.get("prioritizedNextSteps"), list) else [],
        "aiWarnings": list(parsed.get("aiWarnings") or []) if isinstance(parsed.get("aiWarnings"), list) else [],
        "modelInfo": {
            "provider": "bedrock",
            "modelId": model_id,
            "enhanced": True,
        },
    }

    # Ensure advisory note
    if "AI enhancement is advisory only" not in str(out.get("aiWarnings", [])):
        out.setdefault("aiWarnings", [])
        if not isinstance(out["aiWarnings"], list):
            out["aiWarnings"] = []
        out["aiWarnings"].append("AI enhancement is advisory only. Deterministic findings remain authoritative.")

    return out
