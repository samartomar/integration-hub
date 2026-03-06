from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from policy_engine import PolicyDecision  # noqa: E402
from registry_lambda import handler  # noqa: E402


class _AllowlistCursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def execute(self, _query, _params):
        return None

    def fetchone(self):
        return None


class _AllowlistConn:
    def cursor(self, *args, **kwargs):
        return _AllowlistCursor()


class _ConnCtx:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        return None


def _event(query: dict[str, str] | None = None) -> dict:
    return {
        "path": "/v1/registry/policy-simulator",
        "rawPath": "/v1/registry/policy-simulator",
        "httpMethod": "GET",
        "queryStringParameters": query or {},
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "groups": ["integrationhub-admins"],
                    }
                }
            }
        },
    }


@patch("registry_lambda.require_admin_secret", return_value=None)
@patch("registry_lambda.evaluate_policy")
@patch("registry_lambda._get_connection")
def test_admin_can_simulate_decision(mock_conn, mock_eval, _mock_admin) -> None:
    mock_conn.return_value = _ConnCtx(object())
    mock_eval.side_effect = [
        PolicyDecision(
            allow=True,
            http_status=200,
            decision_code="OK",
            message="OK",
            metadata={},
        ),
        PolicyDecision(
            allow=False,
            http_status=403,
            decision_code="ALLOWLIST_DENY",
            message="deny",
            metadata={"matched_policy": "allowlist"},
        ),
    ]

    resp = handler(
        _event(
            {
                "vendorCode": "LH001",
                "operationCode": "get-verify-member-eligibility",
                "targetVendorCode": "VENDOR_B",
                "action": "EXECUTE",
            }
        ),
        None,
    )

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["allowed"] is False
    assert body["decisionCode"] == "ALLOWLIST_DENY"
    assert body["httpStatus"] == 403


@patch(
    "registry_lambda.require_admin_secret",
    return_value={
        "statusCode": 403,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": {"code": "FORBIDDEN", "message": "admin required"}}),
    },
)
def test_non_admin_receives_403(_mock_admin) -> None:
    resp = handler(_event({"action": "EXECUTE"}), None)
    assert resp["statusCode"] == 403


@patch("registry_lambda.require_admin_secret", return_value=None)
@patch("policy_engine.log_policy_decision")
@patch("registry_lambda._get_connection")
def test_simulation_never_logs_entries(mock_conn, mock_log_policy_decision, _mock_admin) -> None:
    mock_conn.return_value = _ConnCtx(object())

    resp = handler(_event({"action": "AUDIT_READ", "vendorCode": "LH001"}), None)

    assert resp["statusCode"] == 200
    # Registry-level auth policy may emit a non-persistent decision (conn=None).
    # Simulator call itself must never pass a DB connection into policy logging.
    assert all(call.args[0] is None for call in mock_log_policy_decision.call_args_list)


@patch("registry_lambda.require_admin_secret", return_value=None)
@patch("registry_lambda._get_connection")
def test_allowlist_deny_scenario_works(mock_conn, _mock_admin) -> None:
    mock_conn.return_value = _ConnCtx(_AllowlistConn())

    resp = handler(
        _event(
            {
                "vendorCode": "LH001",
                "operationCode": "get-verify-member-eligibility",
                "targetVendorCode": "VENDOR_B",
                "action": "EXECUTE",
            }
        ),
        None,
    )

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["allowed"] is False
    assert body["decisionCode"] == "ALLOWLIST_DENY"
    assert body["httpStatus"] == 403


@patch("registry_lambda.require_admin_secret", return_value=None)
@patch("registry_lambda.evaluate_policy")
@patch("registry_lambda._get_connection")
def test_spoof_prevention_scenario_works(mock_conn, mock_eval, _mock_admin) -> None:
    mock_conn.return_value = _ConnCtx(object())

    def _assert_ctx(ctx, *, conn=None):
        # Simulator intentionally ignores any spoof-style source vendor input.
        assert ctx.requested_source_vendor_code is None
        return PolicyDecision(
            allow=True,
            http_status=200,
            decision_code="OK",
            message="OK",
            metadata={},
        )

    mock_eval.side_effect = _assert_ctx

    resp = handler(
        _event(
            {
                "vendorCode": "LH001",
                "operationCode": "get-verify-member-eligibility",
                "targetVendorCode": "VENDOR_B",
                "sourceVendorCode": "SPOOFED",
                "action": "EXECUTE",
            }
        ),
        None,
    )

    assert resp["statusCode"] == 200
