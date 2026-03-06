from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from policy_engine import PolicyContext, PolicyDecision, evaluate_policy, log_policy_decision  # noqa: E402
from registry_lambda import handler  # noqa: E402


class _Cursor:
    def __init__(self, storage: list[tuple], should_fail: bool = False):
        self.storage = storage
        self.should_fail = should_fail

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def execute(self, _query, params):
        if self.should_fail:
            raise RuntimeError("db write failed")
        self.storage.append(params)


class _Conn:
    def __init__(self, storage: list[tuple], should_fail: bool = False):
        self.storage = storage
        self.should_fail = should_fail

    def cursor(self, *args, **kwargs):
        return _Cursor(self.storage, should_fail=self.should_fail)


def _ctx(**overrides):
    base = {
        "surface": "RUNTIME",
        "action": "EXECUTE",
        "vendor_code": "LH001",
        "target_vendor_code": "LH002",
        "operation_code": "GET_RECEIPT",
        "requested_source_vendor_code": None,
        "is_admin": False,
        "groups": [],
        "query": {
            "transaction_id": "tx-1",
            "correlation_id": "corr-1",
            "enforce_allowlist": False,
        },
    }
    base.update(overrides)
    return PolicyContext(**base)


def test_policy_decision_logging_occurs() -> None:
    storage: list[tuple] = []
    conn = _Conn(storage)
    decision = evaluate_policy(_ctx(), conn=conn)
    assert decision.allow is True
    assert len(storage) == 1
    row = storage[0]
    assert row[0] == "RUNTIME"
    assert row[1] == "EXECUTE"
    assert row[5] == decision.decision_code


def test_policy_logging_fail_open() -> None:
    conn = _Conn([], should_fail=True)
    decision = evaluate_policy(_ctx(), conn=conn)
    assert decision.decision_code in ("ALLOWLIST_ALLOW", "OK")


@patch("registry_lambda.require_admin_secret", return_value=None)
@patch("registry_lambda.evaluate_policy")
@patch("registry_lambda._list_policy_decisions")
@patch("registry_lambda._get_connection")
def test_admin_policy_decisions_endpoint_returns_items(
    mock_conn,
    mock_list,
    mock_eval,
    _mock_admin,
) -> None:
    mock_conn.return_value.__enter__.return_value = object()
    mock_eval.return_value = PolicyDecision(
        allow=True,
        http_status=200,
        decision_code="OK",
        message="OK",
        metadata={},
    )
    mock_list.return_value = ([{"decisionCode": "ALLOWLIST_DENY", "allowed": False}], "next")

    event = {
        "path": "/v1/registry/policy-decisions",
        "rawPath": "/v1/registry/policy-decisions",
        "httpMethod": "GET",
        "queryStringParameters": {},
        "requestContext": {"authorizer": {"jwt": {"claims": {"groups": ["integrationhub-admins"]}}}},
    }

    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["count"] == 1
    assert body["items"][0]["decisionCode"] == "ALLOWLIST_DENY"


def test_metadata_never_includes_payload_fields() -> None:
    storage: list[tuple] = []
    conn = _Conn(storage)
    ctx = _ctx(action="REGISTRY_READ")
    decision = PolicyDecision(
        allow=False,
        http_status=403,
        decision_code="ALLOWLIST_DENY",
        message="deny",
        metadata={
            "matched_policy": "allowlist",
            "payload": {"member": "123"},
            "requestBody": {"x": 1},
            "safe": {"note": "ok", "response": {"secret": "n/a"}},
        },
    )

    log_policy_decision(conn, ctx, decision)
    assert len(storage) == 1
    metadata_json = storage[0][10]
    metadata = json.loads(metadata_json)
    assert "payload" not in metadata
    assert "requestBody" not in metadata
    assert "response" not in metadata.get("safe", {})
