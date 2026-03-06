"""Centralized policy evaluation for runtime, admin, and audit surfaces."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Literal


AUTH_REQUIRED = "AUTH_REQUIRED"
AUTH_INVALID = "AUTH_INVALID"
ADMIN_GROUP_REQUIRED = "ADMIN_GROUP_REQUIRED"
VENDOR_CLAIM_MISSING = "VENDOR_CLAIM_MISSING"
VENDOR_SPOOF_BLOCKED = "VENDOR_SPOOF_BLOCKED"
ALLOWLIST_DENY = "ALLOWLIST_DENY"
ALLOWLIST_ALLOW = "ALLOWLIST_ALLOW"
FEATURE_DISABLED = "FEATURE_DISABLED"
PHI_APPROVAL_REQUIRED = "PHI_APPROVAL_REQUIRED"
OK = "OK"

_LOG = logging.getLogger(__name__)
_FORBIDDEN_METADATA_KEYS = {
    "payload",
    "request",
    "response",
    "request_body",
    "response_body",
    "requestbody",
    "responsebody",
    "canonicalrequestbody",
    "targetrequestbody",
    "targetresponsebody",
    "canonicalresponsebody",
    "body",
    "raw",
    "parameters",
    "phi",
    "pii",
}


@dataclass
class PolicyContext:
    surface: Literal["ADMIN", "VENDOR", "RUNTIME"]
    action: Literal[
        "EXECUTE",
        "AI_EXECUTE_DATA",
        "AI_EXECUTE_PROMPT",
        "AUDIT_LIST",
        "AUDIT_READ",
        "AUDIT_EXPAND_SENSITIVE",
        "REGISTRY_READ",
        "REGISTRY_WRITE",
    ]
    vendor_code: str | None
    target_vendor_code: str | None
    operation_code: str | None
    requested_source_vendor_code: str | None
    is_admin: bool
    groups: list[str]
    query: dict[str, Any]


@dataclass
class PolicyDecision:
    allow: bool
    http_status: int
    decision_code: str
    message: str
    metadata: dict[str, Any]


_VENDOR_REQUIRED_ACTIONS = frozenset({
    "EXECUTE",
    "AI_EXECUTE_DATA",
    "AI_EXECUTE_PROMPT",
    "REGISTRY_READ",
    "REGISTRY_WRITE",
})
_ALLOWLIST_ACTIONS = frozenset({"EXECUTE", "AI_EXECUTE_DATA"})


def _sanitize_metadata(value: Any) -> Any:
    """Remove payload-like keys and keep JSON-safe metadata only."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            key = str(k)
            lowered = key.strip().lower()
            if lowered in _FORBIDDEN_METADATA_KEYS:
                continue
            if "payload" in lowered or "request" in lowered or "response" in lowered:
                continue
            out[key] = _sanitize_metadata(v)
        return out
    if isinstance(value, list):
        return [_sanitize_metadata(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def log_policy_decision(conn: Any, ctx: PolicyContext, decision: PolicyDecision) -> None:
    """Best-effort policy decision logging. Fail-open by design."""
    if conn is None:
        return
    metadata = _sanitize_metadata(decision.metadata or {})
    transaction_id = ctx.query.get("transaction_id") or ctx.query.get("transactionId")
    correlation_id = ctx.query.get("correlation_id") or ctx.query.get("correlationId")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO policy.policy_decisions (
                    surface,
                    action,
                    vendor_code,
                    target_vendor_code,
                    operation_code,
                    decision_code,
                    allowed,
                    http_status,
                    correlation_id,
                    transaction_id,
                    metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    ctx.surface,
                    ctx.action,
                    ctx.vendor_code,
                    ctx.target_vendor_code,
                    ctx.operation_code,
                    decision.decision_code,
                    bool(decision.allow),
                    int(decision.http_status),
                    correlation_id,
                    transaction_id,
                    json.dumps(metadata),
                ),
            )
    except Exception as exc:
        _LOG.warning("policy_decision_log_failed", extra={"error": str(exc)})


def _allow(decision_code: str, message: str, metadata: dict[str, Any] | None = None) -> PolicyDecision:
    return PolicyDecision(
        allow=True,
        http_status=200,
        decision_code=decision_code,
        message=message,
        metadata=metadata or {},
    )


def _deny(
    decision_code: str,
    message: str,
    http_status: int,
    *,
    matched_policy: str,
    matched_rule_id: str | None = None,
    notes: str | None = None,
) -> PolicyDecision:
    metadata: dict[str, Any] = {"matched_policy": matched_policy}
    if matched_rule_id:
        metadata["matched_rule_id"] = matched_rule_id
    if notes:
        metadata["notes"] = notes
    return PolicyDecision(
        allow=False,
        http_status=http_status,
        decision_code=decision_code,
        message=message,
        metadata=metadata,
    )


def _allowlist_permits(conn: Any, source_vendor: str, target_vendor: str, operation_code: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM control_plane.vendor_operation_allowlist
            WHERE rule_scope = 'admin'
              AND operation_code = %s
              AND (COALESCE(is_any_source, FALSE) = TRUE OR source_vendor_code = %s)
              AND (COALESCE(is_any_target, FALSE) = TRUE OR target_vendor_code = %s)
              AND flow_direction IN ('INBOUND', 'OUTBOUND', 'BOTH')
            LIMIT 1
            """,
            (operation_code, source_vendor, target_vendor),
        )
        return cur.fetchone() is not None


def _has_group(groups: list[str], group_name: str) -> bool:
    expected = (group_name or "").strip().lower()
    if not expected:
        return False
    return any(str(g).strip().lower() == expected for g in groups or [])


def evaluate_policy(ctx: PolicyContext, *, conn: Any = None) -> PolicyDecision:
    """Evaluate policy rules in deterministic order and return decision."""

    def _finalize(decision: PolicyDecision) -> PolicyDecision:
        if bool(ctx.query.get("log_decision", True)):
            log_policy_decision(conn, ctx, decision)
        return decision

    # 1) auth/vendor claim presence (for actions needing vendor identity)
    if ctx.action in _VENDOR_REQUIRED_ACTIONS and not (ctx.vendor_code or "").strip():
        return _finalize(
            _deny(
                VENDOR_CLAIM_MISSING,
                "Vendor identity is required",
                403,
                matched_policy="vendor_identity",
                matched_rule_id="vendor-claim-required",
            )
        )

    # 2) spoof prevention (body source cannot override authenticated vendor)
    requested = (ctx.requested_source_vendor_code or "").strip()
    actual = (ctx.vendor_code or "").strip()
    if requested and actual and requested.upper() != actual.upper():
        return _finalize(
            _deny(
                VENDOR_SPOOF_BLOCKED,
                "sourceVendorCode does not match authenticated vendor",
                403,
                matched_policy="spoof_prevention",
                matched_rule_id="source-vendor-match",
            )
        )

    # 3) admin group required (admin surface)
    if ctx.surface == "ADMIN":
        if not ctx.is_admin:
            return _finalize(
                _deny(
                    ADMIN_GROUP_REQUIRED,
                    "Admin access is required",
                    403,
                    matched_policy="admin_guard",
                    matched_rule_id="admin-required",
                )
            )

    # 4) allowlist check for runtime execute and AI execute data
    if ctx.action in _ALLOWLIST_ACTIONS:
        src = (ctx.vendor_code or "").strip()
        tgt = (ctx.target_vendor_code or "").strip()
        op = (ctx.operation_code or "").strip()
        enforce_allowlist = bool(ctx.query.get("enforce_allowlist", True))
        if src and tgt and op:
            if conn is None or not enforce_allowlist:
                return _finalize(
                    _allow(
                        ALLOWLIST_ALLOW,
                        "OK",
                        metadata={
                            "matched_policy": "allowlist",
                            "matched_rule_id": "deferred-to-runtime-validation",
                            "notes": "Allowlist is validated by existing runtime control-plane checks",
                        },
                    )
                )
            if not _allowlist_permits(conn, src, tgt, op):
                return _finalize(
                    _deny(
                        ALLOWLIST_DENY,
                        f"Allowlist violation: {src} -> {tgt} for {op} not permitted",
                        403,
                        matched_policy="allowlist",
                        matched_rule_id="admin-allowlist",
                    )
                )

    # 5) feature gates (AI formatter gate is informational and must not flip execute)
    if ctx.action == "AI_EXECUTE_PROMPT":
        return _finalize(
            _allow(
                OK,
                "OK",
                metadata={
                    "matched_policy": "feature_gate",
                    "matched_rule_id": "ai-formatter-readonly",
                    "notes": "AI formatter gating is non-blocking for execute outcome",
                },
            )
        )

    # 6) PHI expand gating
    if ctx.action == "AUDIT_EXPAND_SENSITIVE" or bool(ctx.query.get("expandSensitive")):
        phi_group = (os.environ.get("PHI_APPROVED_GROUP") or "PHI_APPROVED").strip()
        if not _has_group(ctx.groups, phi_group):
            return _finalize(
                _deny(
                    PHI_APPROVAL_REQUIRED,
                    "expandSensitive requires PHI-approved access",
                    403,
                    matched_policy="phi_access",
                    matched_rule_id="phi-approved-group",
                )
            )

    return _finalize(_allow(OK, "OK", metadata={"matched_policy": "default"}))
