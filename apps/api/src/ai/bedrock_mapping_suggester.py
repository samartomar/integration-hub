"""Bedrock mapping suggester - runs INSIDE AI Gateway Lambda only.

Builds redacted mapping context prompt, calls Bedrock, returns structured suggestion.
PHI-safe: no raw payload bodies, only field names, schemas, and mapping summaries.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from ai.bedrock_client import invoke_model

_ADVISORY_NOTE = "Suggestion is advisory only and has not been applied."


def _redact_value(val: Any) -> Any:
    """Replace user-provided values with placeholders. Keep structure, redact literals."""
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return "[NUMBER]" if isinstance(val, (int, float)) and abs(val) > 100 else val
    if isinstance(val, str):
        if re.search(r"\d{3}-\d{2}-\d{4}", val):
            return "[REDACTED]"
        if re.search(r"[A-Z]{2}\d{3}-\d+", val):
            return "[REDACTED]"
        if len(val) > 50:
            return val[:20] + "...[truncated]"
        return val
    if isinstance(val, dict):
        return {k: _redact_value(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_redact_value(v) for v in val[:10]]
    return val


def build_redacted_mapping_prompt(payload: dict[str, Any]) -> str:
    """
    Build PHI-safe prompt for mapping suggestion.

    Includes: operationCode, version, sourceVendor, targetVendor, direction,
    canonical schema (field names only), vendor shape (field names only),
    existing mapping summary. Excludes raw payload values.
    """
    op = (payload.get("operationCode") or payload.get("operation_code") or "").strip()
    version = (payload.get("version") or "").strip() or "1.0"
    source = (payload.get("sourceVendor") or payload.get("source_vendor") or "").strip()
    target = (payload.get("targetVendor") or payload.get("target_vendor") or "").strip()
    direction = (payload.get("direction") or "").strip().upper()

    canonical_schema = payload.get("canonicalSchema") or {}
    vendor_shape = payload.get("vendorShape") or payload.get("vendor_shape") or {}
    existing = payload.get("existingMappingDefinition") or {}

    # Extract only field names / structure, no values
    def _field_names(obj: Any) -> Any:
        if isinstance(obj, dict):
            if "properties" in obj:
                return list((obj.get("properties") or {}).keys())
            if "required" in obj:
                return {"required": obj["required"], "properties": list((obj.get("properties") or {}).keys())}
            return {k: _field_names(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_field_names(v) for v in obj[:20]]
        return obj

    canonical_fields = _field_names(canonical_schema) if canonical_schema else []
    vendor_fields = _field_names(vendor_shape) if vendor_shape else []

    # Existing mapping: only structure, no selectors with real values
    existing_safe: dict[str, Any] = {}
    if isinstance(existing, dict):
        for k, v in existing.items():
            if isinstance(v, str) and v.strip().startswith("$."):
                existing_safe[k] = "[path]"
            else:
                existing_safe[k] = "[constant]"

    safe_context = {
        "operationCode": op,
        "version": version,
        "sourceVendor": source,
        "targetVendor": target,
        "direction": direction,
        "canonicalFieldNames": canonical_fields if isinstance(canonical_fields, list) else canonical_fields,
        "vendorFieldNames": vendor_fields if isinstance(vendor_fields, list) else vendor_fields,
        "existingMappingSummary": existing_safe,
    }

    return json.dumps(safe_context, indent=2)


def maybe_should_use_mapping_ai(
    request_payload_or_flag: dict[str, Any] | bool | None,
    env_config: dict[str, str] | None = None,
) -> bool:
    """
    Decide whether to use Bedrock for mapping suggestion.

    - BEDROCK_MAPPING_SUGGEST_ENABLED must be truthy
    - BEDROCK_MAPPING_SUGGEST_MODEL_ID must be set
    - In local/dev, skip unless BEDROCK_MAPPING_SUGGEST_ALLOW_LOCAL is set
    """
    cfg = env_config or {}
    enabled = (
        (cfg.get("BEDROCK_MAPPING_SUGGEST_ENABLED") or os.environ.get("BEDROCK_MAPPING_SUGGEST_ENABLED", ""))
        .strip()
        .lower()
        in ("true", "1", "yes")
    )
    model_id = (
        (cfg.get("BEDROCK_MAPPING_SUGGEST_MODEL_ID") or os.environ.get("BEDROCK_MAPPING_SUGGEST_MODEL_ID", ""))
        .strip()
    )
    run_env = (cfg.get("RUN_ENV") or os.environ.get("RUN_ENV", "")).strip().lower()
    allow_local = (
        (cfg.get("BEDROCK_MAPPING_SUGGEST_ALLOW_LOCAL") or os.environ.get("BEDROCK_MAPPING_SUGGEST_ALLOW_LOCAL", ""))
        .strip()
        .lower()
        in ("true", "1", "yes")
    )

    if not enabled or not model_id:
        return False
    if run_env == "local" and not allow_local:
        return False

    if isinstance(request_payload_or_flag, bool):
        return request_payload_or_flag
    if isinstance(request_payload_or_flag, dict):
        return request_payload_or_flag.get("suggestWithAi") is True
    return False


def suggest_mapping_with_bedrock(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Call Bedrock for mapping suggestion. Returns structured suggestion or fallback.

    Runs only inside AI Gateway Lambda. PHI-safe prompt.
    """
    enabled = (
        (os.environ.get("BEDROCK_MAPPING_SUGGEST_ENABLED") or "").strip().lower()
        in ("true", "1", "yes")
    )
    model_id = (os.environ.get("BEDROCK_MAPPING_SUGGEST_MODEL_ID") or "").strip()
    timeout_ms = int(os.environ.get("BEDROCK_MAPPING_SUGGEST_TIMEOUT_MS", "8000"))
    run_env = (os.environ.get("RUN_ENV") or "").strip().lower()
    allow_local = (
        (os.environ.get("BEDROCK_MAPPING_SUGGEST_ALLOW_LOCAL") or "").strip().lower()
        in ("true", "1", "yes")
    )

    if not enabled or not model_id:
        return _fallback_suggestion("disabled_or_unavailable")
    if run_env == "local" and not allow_local:
        return _fallback_suggestion("local_skip")

    prompt = build_redacted_mapping_prompt(payload)
    system = (
        "You are a technical assistant for data mapping. Given canonical and vendor field names "
        "and an existing mapping summary, suggest field mappings as a JSON object. "
        "Output valid JSON only with: summary (string), proposedFieldMappings (array of {from, to}), "
        "proposedConstants (array), warnings (array of strings), confidence (low|medium|high). "
        "Do not include raw payload values. Suggestion is advisory only."
    )

    body: dict[str, Any] = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "temperature": 0.2,
        "system": system[:4096],
        "messages": [{"role": "user", "content": (prompt or "")[:8192]}],
    }

    try:
        raw = invoke_model(
            model_id,
            body,
            timeout_seconds=timeout_ms / 1000.0 if timeout_ms else None,
        )
    except Exception as e:
        return _fallback_suggestion("bedrock_error", str(e)[:200])

    return _parse_suggestion_response(raw, model_id)


def _fallback_suggestion(reason: str, detail: str | None = None) -> dict[str, Any]:
    """Return fallback when Bedrock is unavailable."""
    warnings = ["AI mapping suggestion unavailable; deterministic baseline only."]
    if detail:
        warnings.append(detail[:200])
    return {
        "summary": None,
        "proposedFieldMappings": [],
        "proposedConstants": [],
        "warnings": warnings,
        "confidence": "none",
        "modelInfo": {"provider": "bedrock", "enhanced": False, "reason": reason},
    }


def _parse_suggestion_response(raw: str, model_id: str) -> dict[str, Any]:
    """Parse model output into suggestion contract. Handles malformed JSON safely."""
    raw = (raw or "").strip()
    if not raw:
        return _fallback_suggestion("empty_response")

    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    if json_match:
        raw = json_match.group(1).strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return _fallback_suggestion("malformed_response")

    if not isinstance(parsed, dict):
        return _fallback_suggestion("malformed_response")

    proposed = parsed.get("proposedFieldMappings") or []
    if not isinstance(proposed, list):
        proposed = []

    out: dict[str, Any] = {
        "summary": (parsed.get("summary") or "").strip() or None,
        "proposedFieldMappings": [
            {"from": str(m.get("from", "")), "to": str(m.get("to", ""))}
            for m in proposed
            if isinstance(m, dict) and (m.get("from") or m.get("to"))
        ],
        "proposedConstants": (
            parsed.get("proposedConstants")
            if isinstance(parsed.get("proposedConstants"), list)
            else []
        ),
        "warnings": list(parsed.get("warnings") or []) if isinstance(parsed.get("warnings"), list) else [],
        "confidence": (parsed.get("confidence") or "medium").strip().lower()
        if isinstance(parsed.get("confidence"), str)
        else "medium",
        "modelInfo": {"provider": "bedrock", "modelId": model_id, "enhanced": True},
    }

    if _ADVISORY_NOTE not in str(out.get("warnings", [])):
        out.setdefault("warnings", [])
        if not isinstance(out["warnings"], list):
            out["warnings"] = []
        out["warnings"].append(_ADVISORY_NOTE)

    return out
