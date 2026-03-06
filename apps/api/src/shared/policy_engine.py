"""Phase 1 policy engine.

This module provides a lightweight wrapper that standardizes policy decisions
while allowing existing checks (allowlist/auth) to remain the source of truth.
"""

from __future__ import annotations

from typing import Any, TypedDict


class PolicyDecision(TypedDict, total=False):
    """Decision envelope returned by evaluate_policy."""

    allowed: bool
    policy: str
    reason: str
    details: dict[str, Any]
    response: dict[str, Any]


def evaluate_policy(context: dict[str, Any]) -> PolicyDecision:
    """Evaluate policy using context and optional existing check callback.

    Phase 1 behavior:
    - If `check`/`allowlist_check`/`auth_check` callable exists, execute it.
    - Preserve existing logic: callback decides pass/fail.
    - Normalize output to a consistent decision object.
    """

    policy_name = str(context.get("policy") or "UNSPECIFIED_POLICY")
    details = context.get("details")
    decision: PolicyDecision = {
        "allowed": True,
        "policy": policy_name,
        "reason": "ALLOWED",
    }
    if isinstance(details, dict):
        decision["details"] = details

    check = context.get("check") or context.get("allowlist_check") or context.get("auth_check")
    if not callable(check):
        # Phase 1 is permissive unless an explicit check is provided.
        if context.get("default_allow", True):
            return decision
        decision["allowed"] = False
        decision["reason"] = str(context.get("deny_reason") or "POLICY_DENIED")
        return decision

    try:
        result = check()
    except Exception as exc:  # Existing checks may raise ValueError/Auth errors.
        decision["allowed"] = False
        decision["reason"] = str(exc) or "POLICY_DENIED"
        return decision

    if result is None or result is True:
        return decision

    if result is False:
        decision["allowed"] = False
        decision["reason"] = str(context.get("deny_reason") or "POLICY_DENIED")
        return decision

    if isinstance(result, str):
        decision["allowed"] = False
        decision["reason"] = result
        return decision

    if isinstance(result, dict):
        if "allowed" in result:
            decision["allowed"] = bool(result.get("allowed"))
        if "reason" in result:
            decision["reason"] = str(result.get("reason"))
        if isinstance(result.get("details"), dict):
            decision["details"] = result["details"]
        if isinstance(result.get("response"), dict):
            decision["response"] = result["response"]
        return decision

    # Unknown return type from callback -> deny to fail closed.
    decision["allowed"] = False
    decision["reason"] = "POLICY_CHECK_INVALID_RESULT"
    return decision
