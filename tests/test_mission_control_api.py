from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from registry_lambda import handler  # noqa: E402


JWT_ADMIN = {
    "principalId": "okta|admin",
    "jwt": {"claims": {"sub": "okta|admin", "aud": "api://default", "groups": ["integrationhub-admins"]}},
}
JWT_NON_ADMIN = {
    "principalId": "okta|user",
    "jwt": {"claims": {"sub": "okta|user", "aud": "api://default", "groups": ["viewer"]}},
}


def _event(path: str, query: dict[str, str] | None = None, authorizer: dict | None = None) -> dict:
    return {
        "path": path,
        "rawPath": path,
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": query or {},
        "pathParameters": {},
        "requestContext": {"http": {"method": "GET"}, "authorizer": authorizer} if authorizer else {},
    }


@patch("registry_lambda._get_connection")
def test_admin_access_topology_works(mock_conn) -> None:
    cur = mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur.fetchall.side_effect = [
        [{"vendor_code": "LH001", "vendor_name": "Vendor 1"}],
        [],
    ]

    resp = handler(
        _event("/v1/registry/mission-control/topology", authorizer=JWT_ADMIN),
        None,
    )
    assert resp["statusCode"] == 200


def test_non_admin_denied(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_REQUIRED_ROLE", "integrationhub-admins")
    resp = handler(
        _event("/v1/registry/mission-control/topology", authorizer=JWT_NON_ADMIN),
        None,
    )
    assert resp["statusCode"] in (401, 403)


@patch("registry_lambda._get_connection")
def test_activity_returns_metadata_only(mock_conn) -> None:
    cur = mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur.fetchall.side_effect = [
        [
            {
                "created_at": "2026-03-05T12:00:00Z",
                "transaction_id": "tx-1",
                "correlation_id": "corr-1",
                "source_vendor": "LH001",
                "target_vendor": "LH002",
                "operation": "GET_RECEIPT",
                "status": "success",
                "http_status": 200,
                "request_body": {"x": "should-not-leak"},
            }
        ],
        [
            {
                "occurred_at": "2026-03-05T12:00:01Z",
                "transaction_id": "tx-2",
                "correlation_id": "corr-2",
                "vendor_code": "LH001",
                "target_vendor_code": "LH003",
                "operation_code": "GET_RECEIPT",
                "decision_code": "ALLOWLIST_DENY",
                "http_status": 403,
                "payload": {"sensitive": True},
            }
        ],
    ]

    resp = handler(
        _event("/v1/registry/mission-control/activity", authorizer=JWT_ADMIN),
        None,
    )
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    forbidden = {"request_body", "response_body", "debug_payload", "payload"}
    for item in body.get("items", []):
        assert forbidden.isdisjoint(set(item.keys()))


@patch("registry_lambda._get_connection")
def test_lookback_clamp_enforced(mock_conn) -> None:
    cur = mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur.fetchall.side_effect = [[], []]

    resp = handler(
        _event(
            "/v1/registry/mission-control/activity",
            query={"lookbackMinutes": "500"},
            authorizer=JWT_ADMIN,
        ),
        None,
    )
    assert resp["statusCode"] == 200
    args = cur.execute.call_args_list[0][0][1]
    assert args[0] <= 60
    body = json.loads(resp["body"])
    assert body["lookbackMinutes"] <= 60


@patch("registry_lambda._get_connection")
def test_limit_clamp_enforced(mock_conn) -> None:
    cur = mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur.fetchall.side_effect = [[], []]

    resp = handler(
        _event(
            "/v1/registry/mission-control/activity",
            query={"limit": "1000"},
            authorizer=JWT_ADMIN,
        ),
        None,
    )
    assert resp["statusCode"] == 200
    tx_args = cur.execute.call_args_list[0][0][1]
    policy_args = cur.execute.call_args_list[1][0][1]
    assert tx_args[1] <= 200
    assert policy_args[1] <= 200
