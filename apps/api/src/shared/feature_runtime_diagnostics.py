"""Syntegris feature runtime diagnostics - configuration self-check.

Validates required env/config for the current Syntegris feature set.
No secrets exposure. No persistence. Admin-only.
"""

from __future__ import annotations

import os
from typing import Any

DIAGNOSTICS_NOTE = "Diagnostics are configuration-only and do not expose secrets."


def get_syntegris_feature_diagnostics() -> dict[str, Any]:
    """Validate required env/config for Syntegris features. Returns status, checks, notes."""
    checks: list[dict[str, Any]] = []

    # AI Gateway invoke wiring
    fn_arn = (os.environ.get("AI_GATEWAY_FUNCTION_ARN") or "").strip()
    if fn_arn:
        checks.append({
            "code": "AI_GATEWAY_FUNCTION_ARN_SET",
            "status": "PASS",
            "message": "AI gateway internal invoke target is configured.",
        })
    else:
        checks.append({
            "code": "AI_GATEWAY_FUNCTION_ARN_SET",
            "status": "WARN",
            "message": "AI_GATEWAY_FUNCTION_ARN not set. AI formatter/debugger invoke may fail.",
        })

    # Bedrock debugger
    debugger_enabled = (os.environ.get("BEDROCK_DEBUGGER_ENABLED") or "").strip().lower() in ("true", "1", "yes")
    debugger_model = (os.environ.get("BEDROCK_DEBUGGER_MODEL_ID") or "").strip()
    if debugger_enabled and debugger_model:
        checks.append({
            "code": "BEDROCK_DEBUGGER_MODEL_ID_SET",
            "status": "PASS",
            "message": "Bedrock debugger enhancement is configured.",
        })
    elif debugger_enabled and not debugger_model:
        checks.append({
            "code": "BEDROCK_DEBUGGER_MODEL_ID_SET",
            "status": "WARN",
            "message": "Bedrock debugger is enabled but BEDROCK_DEBUGGER_MODEL_ID is not set.",
        })
    else:
        checks.append({
            "code": "BEDROCK_DEBUGGER_MODEL_ID_SET",
            "status": "WARN",
            "message": "Bedrock debugger enhancement is disabled (BEDROCK_DEBUGGER_ENABLED not true).",
        })

    # IDP / JWT
    idp_issuer = (os.environ.get("IDP_ISSUER") or "").strip()
    if idp_issuer:
        checks.append({
            "code": "IDP_ISSUER_SET",
            "status": "PASS",
            "message": "IDP_ISSUER is configured for JWT validation.",
        })
    else:
        checks.append({
            "code": "IDP_ISSUER_SET",
            "status": "WARN",
            "message": "IDP_ISSUER not set. JWT auth may be disabled or use fallback.",
        })

    # DB (presence only, no connection)
    db_url = (os.environ.get("DB_URL") or "").strip()
    db_secret = (os.environ.get("DB_SECRET_ARN") or "").strip()
    if db_url or db_secret:
        checks.append({
            "code": "DB_CONFIG_SET",
            "status": "PASS",
            "message": "Database configuration is present.",
        })
    else:
        checks.append({
            "code": "DB_CONFIG_SET",
            "status": "WARN",
            "message": "Neither DB_URL nor DB_SECRET_ARN is set. Registry operations may fail.",
        })

    # Runtime API URL (for canonical bridge)
    runtime_url = (os.environ.get("RUNTIME_API_URL") or "").strip()
    if runtime_url:
        checks.append({
            "code": "RUNTIME_API_URL_SET",
            "status": "PASS",
            "message": "RUNTIME_API_URL is configured for canonical bridge execution.",
        })
    else:
        checks.append({
            "code": "RUNTIME_API_URL_SET",
            "status": "WARN",
            "message": "RUNTIME_API_URL not set. Canonical bridge execute may fail.",
        })

    status = "OK" if all(c.get("status") == "PASS" for c in checks) else "WARN"
    return {
        "status": status,
        "checks": checks,
        "notes": [DIAGNOSTICS_NOTE],
    }


def summarize_syntegris_feature_diagnostics() -> dict[str, Any]:
    """Return summary of diagnostics (pass count, warn count)."""
    diag = get_syntegris_feature_diagnostics()
    checks = diag.get("checks") or []
    pass_count = sum(1 for c in checks if c.get("status") == "PASS")
    warn_count = sum(1 for c in checks if c.get("status") == "WARN")
    return {
        "status": diag.get("status", "WARN"),
        "passCount": pass_count,
        "warnCount": warn_count,
        "totalChecks": len(checks),
    }
