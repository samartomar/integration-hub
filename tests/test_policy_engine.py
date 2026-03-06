from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from policy_engine import (  # noqa: E402
    ADMIN_GROUP_REQUIRED,
    ALLOWLIST_ALLOW,
    ALLOWLIST_DENY,
    OK,
    PHI_APPROVAL_REQUIRED,
    VENDOR_CLAIM_MISSING,
    VENDOR_SPOOF_BLOCKED,
    PolicyContext,
    evaluate_policy,
)


class _FakeCursor:
    def __init__(self, allow: bool):
        self._allow = allow

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def execute(self, _query, _params):
        return None

    def fetchone(self):
        return (1,) if self._allow else None


class _FakeConn:
    def __init__(self, allow: bool):
        self._allow = allow

    def cursor(self):
        return _FakeCursor(self._allow)


def _ctx(**kwargs):
    base = dict(
        surface="RUNTIME",
        action="EXECUTE",
        vendor_code="LH001",
        target_vendor_code="LH002",
        operation_code="GET_RECEIPT",
        requested_source_vendor_code=None,
        is_admin=False,
        groups=[],
        query={},
    )
    base.update(kwargs)
    return PolicyContext(**base)


def test_missing_vendor_claim_denied():
    decision = evaluate_policy(_ctx(vendor_code=None))
    assert decision.allow is False
    assert decision.decision_code == VENDOR_CLAIM_MISSING


def test_spoof_mismatch_denied():
    decision = evaluate_policy(_ctx(requested_source_vendor_code="LH999"))
    assert decision.allow is False
    assert decision.decision_code == VENDOR_SPOOF_BLOCKED


def test_allowlist_missing_denied():
    decision = evaluate_policy(_ctx(), conn=_FakeConn(allow=False))
    assert decision.allow is False
    assert decision.decision_code == ALLOWLIST_DENY


def test_allowlist_present_allowed():
    decision = evaluate_policy(_ctx(), conn=_FakeConn(allow=True))
    assert decision.allow is True
    assert decision.decision_code in (ALLOWLIST_ALLOW, OK)


@patch.dict("os.environ", {"PHI_APPROVED_GROUP": "phi-approved"}, clear=False)
def test_expand_sensitive_requires_phi_group():
    decision = evaluate_policy(
        _ctx(
            surface="VENDOR",
            action="AUDIT_EXPAND_SENSITIVE",
            query={"expandSensitive": True},
            operation_code=None,
            target_vendor_code=None,
        )
    )
    assert decision.allow is False
    assert decision.decision_code == PHI_APPROVAL_REQUIRED


@patch.dict("os.environ", {"PHI_APPROVED_GROUP": "phi-approved"}, clear=False)
def test_expand_sensitive_allows_phi_group():
    decision = evaluate_policy(
        _ctx(
            surface="VENDOR",
            action="AUDIT_EXPAND_SENSITIVE",
            groups=["phi-approved"],
            query={"expandSensitive": True},
            operation_code=None,
            target_vendor_code=None,
        )
    )
    assert decision.allow is True
    assert decision.decision_code == OK


def test_admin_surface_requires_admin():
    decision = evaluate_policy(
        _ctx(
            surface="ADMIN",
            action="REGISTRY_READ",
            is_admin=False,
            operation_code=None,
            target_vendor_code=None,
        )
    )
    assert decision.allow is False
    assert decision.decision_code == ADMIN_GROUP_REQUIRED


def test_ai_formatter_precedence_non_blocking():
    decision = evaluate_policy(
        _ctx(
            action="AI_EXECUTE_PROMPT",
            operation_code="GET_RECEIPT",
            target_vendor_code="LH002",
        ),
        conn=_FakeConn(allow=False),
    )
    assert decision.allow is True
    assert decision.decision_code == OK

