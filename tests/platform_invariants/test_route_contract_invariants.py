"""Platform invariant tests: route contract.

Invariants:
10. Vendor routes expected by UI exist
11. Admin mission control routes are protected by admin auth/group
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "apps" / "api" / "src" / "lambda"))

from vendor_registry_jwt import add_jwt_auth  # noqa: E402

JWT_ADMIN = {
    "principalId": "okta|admin",
    "jwt": {"claims": {"sub": "okta|admin", "aud": "api://default", "groups": ["integrationhub-admins"]}},
}
JWT_NON_ADMIN = {
    "principalId": "okta|user",
    "jwt": {"claims": {"sub": "okta|user", "aud": "api://default", "groups": ["viewer"]}},
}


def _vendor_event(path: str, method: str = "GET", body: dict | None = None) -> dict:
    segments = path.strip("/").split("/")
    proxy = "/".join(segments[2:]) if len(segments) >= 3 else ""
    evt = {
        "path": path,
        "rawPath": path,
        "httpMethod": method,
        "pathParameters": {"proxy": proxy},
        "queryStringParameters": {"status": "PENDING"} if "change-requests" in path else {},
        "requestContext": {"http": {"method": method}},
        "headers": {},
        "body": json.dumps(body) if body else None,
    }
    return evt


@patch("vendor_registry_lambda._get_connection")
def test_vendor_my_change_requests_route_exists(mock_conn_ctx: MagicMock) -> None:
    """Invariant 10: /v1/vendor/my-change-requests exists."""
    from vendor_registry_lambda import handler  # noqa: E402

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    cursor.fetchone.return_value = ("LH001", True)
    cursor.fetchall.return_value = []
    mock_conn.cursor.return_value = cursor

    event = _vendor_event("/v1/vendor/my-change-requests")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] != 404


@patch("vendor_registry_lambda._get_connection")
def test_vendor_allowlist_change_requests_route_exists(mock_conn_ctx: MagicMock) -> None:
    """Invariant 10: /v1/vendor/allowlist-change-requests exists (POST)."""
    from vendor_registry_lambda import handler  # noqa: E402

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    cursor.fetchone.return_value = ("LH001", True)
    cursor.fetchall.return_value = []
    cursor.execute.side_effect = None
    mock_conn.cursor.return_value = cursor

    event = _vendor_event("/v1/vendor/allowlist-change-requests", "POST", {"rules": []})
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] != 404


@patch("vendor_registry_lambda._get_connection")
def test_vendor_platform_features_route_exists(mock_conn_ctx: MagicMock) -> None:
    """Invariant 10: /v1/vendor/platform/features exists."""
    from vendor_registry_lambda import handler  # noqa: E402

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    cursor.fetchone.return_value = ("LH001", True)
    cursor.fetchall.return_value = []
    mock_conn.cursor.return_value = cursor

    event = _vendor_event("/v1/vendor/platform/features")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] != 404


@patch("vendor_registry_lambda._get_connection")
def test_vendor_policy_preview_route_exists(mock_conn_ctx: MagicMock) -> None:
    """Invariant 10: /v1/vendor/policy/preview exists."""
    from vendor_registry_lambda import handler  # noqa: E402

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    cursor.fetchone.return_value = ("LH001", True)
    cursor.fetchall.return_value = []
    mock_conn.cursor.return_value = cursor

    event = _vendor_event("/v1/vendor/policy/preview", "POST", {"operationCode": "GET_RECEIPT", "targetVendorCode": "LH002"})
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] != 404


@patch("registry_lambda._get_connection")
def test_admin_mission_control_protected_by_admin_auth(mock_conn: MagicMock, monkeypatch) -> None:
    """Invariant 11: Admin mission control routes require admin auth/group."""
    monkeypatch.setenv("ADMIN_REQUIRED_ROLE", "integrationhub-admins")
    from registry_lambda import handler  # noqa: E402

    cur = mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur.fetchall.return_value = []

    def _evt(path: str, authorizer: dict | None) -> dict:
        return {
            "path": path,
            "rawPath": path,
            "httpMethod": "GET",
            "queryStringParameters": {},
            "pathParameters": {},
            "requestContext": {"http": {"method": "GET"}, "authorizer": authorizer} if authorizer else {},
            "headers": {},
            "body": None,
        }

    resp_admin = handler(_evt("/v1/registry/mission-control/topology", JWT_ADMIN), None)
    resp_non_admin = handler(_evt("/v1/registry/mission-control/topology", JWT_NON_ADMIN), None)

    assert resp_admin["statusCode"] == 200
    assert resp_non_admin["statusCode"] in (401, 403)
