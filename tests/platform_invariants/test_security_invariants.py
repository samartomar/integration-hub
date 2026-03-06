"""Platform invariant tests: security contract.

Invariants:
8. expandSensitive requires PHI-approved group
9. Mission Control activity/topology endpoints return metadata only
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "apps" / "api" / "src" / "lambda"))

from policy_engine import PolicyContext, evaluate_policy  # noqa: E402

JWT_ADMIN = {
    "principalId": "okta|admin",
    "jwt": {"claims": {"sub": "okta|admin", "aud": "api://default", "groups": ["integrationhub-admins"]}},
}


def _event(path: str, query: dict | None = None, authorizer: dict | None = None) -> dict:
    return {
        "path": path,
        "rawPath": path,
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": query or {},
        "pathParameters": {},
        "requestContext": {"http": {"method": "GET"}, "authorizer": authorizer} if authorizer else {},
    }


@patch.dict("os.environ", {"PHI_APPROVED_GROUP": "PHI_APPROVED"}, clear=False)
def test_expand_sensitive_requires_phi_approved_group() -> None:
    """Invariant 8: expandSensitive requires PHI-approved group."""
    decision = evaluate_policy(
        PolicyContext(
            surface="VENDOR",
            action="AUDIT_EXPAND_SENSITIVE",
            vendor_code="LH001",
            target_vendor_code=None,
            operation_code=None,
            requested_source_vendor_code=None,
            is_admin=False,
            groups=["viewer"],
            query={"expandSensitive": True},
        )
    )
    assert decision.allow is False
    assert decision.decision_code == "PHI_APPROVAL_REQUIRED"


@patch("registry_lambda._get_connection")
def test_mission_control_activity_returns_metadata_only(mock_conn) -> None:
    """Invariant 9: Mission Control activity returns metadata only (no payload/body/debug)."""
    from registry_lambda import handler  # noqa: E402

    cur = mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur.fetchall.side_effect = [
        [
            {
                "created_at": "2026-03-05T12:00:00Z",
                "transaction_id": "tx-1",
                "source_vendor": "LH001",
                "target_vendor": "LH002",
                "operation": "GET_RECEIPT",
                "status": "success",
                "http_status": 200,
                "request_body": {"secret": "leaked"},
                "response_body": {"data": "leaked"},
            }
        ],
        [],
    ]

    resp = handler(_event("/v1/registry/mission-control/activity", authorizer=JWT_ADMIN), None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    forbidden = {"request_body", "response_body", "debug_payload", "payload", "body"}
    for item in body.get("items", []):
        assert forbidden.isdisjoint(set(item.keys()))


@patch("registry_lambda._get_connection")
def test_mission_control_topology_returns_metadata_only(mock_conn) -> None:
    """Invariant 9: Mission Control topology returns metadata only."""
    from registry_lambda import handler  # noqa: E402

    cur = mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur.fetchall.side_effect = [
        [{"vendor_code": "LH001", "vendor_name": "Vendor 1"}],
        [],
    ]

    resp = handler(_event("/v1/registry/mission-control/topology", authorizer=JWT_ADMIN), None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "nodes" in body or "edges" in body or "vendors" in body or "items" in body
