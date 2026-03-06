"""Tests for allowlist change requests flow (allowlist_change_requests table)."""

from __future__ import annotations

import json
import os
import sys
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from vendor_registry_lambda import handler as vendor_handler  # noqa: E402
from vendor_registry_jwt import add_jwt_auth  # noqa: E402


def _post_allowlist_change_request_event(
    direction: str = "OUTBOUND",
    operation_code: str = "GET_WEATHER",
    target_vendor_codes: list[str] | None = None,
    use_wildcard_target: bool = False,
    request_type: str = "PROVIDER_NARROWING",
) -> dict:
    body = {
        "direction": direction,
        "operationCode": operation_code,
        "targetVendorCodes": target_vendor_codes or ["LH001"],
        "useWildcardTarget": use_wildcard_target,
        "ruleScope": "vendor",
        "requestType": request_type,
    }
    return {
        "path": "/v1/vendor/allowlist-change-requests",
        "rawPath": "/v1/vendor/allowlist-change-requests",
        "httpMethod": "POST",
        "pathParameters": {},
        "requestContext": {"http": {"method": "POST"}, "requestId": "test-req-id"},
        "headers": {},
        "body": json.dumps(body),
    }


@patch("vendor_registry_lambda._get_connection")
def test_post_allowlist_change_requests_201(
    mock_conn_ctx: MagicMock,
) -> None:
    """POST /v1/vendor/allowlist-change-requests with valid body returns 201."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        ("BCBSA", True),  # vendor validation
        {"x": 1},  # operation exists check
        {"id": "acr-uuid-1", "status": "PENDING", "created_at": datetime(2026, 2, 25, 12, 0, tzinfo=timezone.utc)},
    ]
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    event = _post_allowlist_change_request_event(
        direction="OUTBOUND",
        operation_code="GET_JOKE_DEMO",
        target_vendor_codes=["LH001"],
        request_type="PROVIDER_NARROWING",
    )
    add_jwt_auth(event, "LH001")
    resp = vendor_handler(event, None)

    assert resp["statusCode"] == 201
    body = json.loads(resp["body"])
    assert body.get("id") == "acr-uuid-1"
    assert body.get("status") == "PENDING"
    assert "transactionId" in body or "id" in body


@patch("vendor_registry_lambda._get_connection")
def test_post_allowlist_change_requests_missing_operation_400(
    mock_conn_ctx: MagicMock,
) -> None:
    """POST without operationCode returns 400."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("BCBSA", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    event = _post_allowlist_change_request_event(operation_code="")
    event["body"] = json.dumps({
        "direction": "OUTBOUND",
        "targetVendorCodes": ["LH001"],
        "useWildcardTarget": False,
        "ruleScope": "vendor",
        "requestType": "ALLOWLIST_RULE",
    })
    add_jwt_auth(event, "LH001")
    resp = vendor_handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "VALIDATION_ERROR"


@patch("vendor_registry_lambda._get_connection")
def test_post_allowlist_change_requests_invalid_direction_400(
    mock_conn_ctx: MagicMock,
) -> None:
    """POST with invalid direction returns 400."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("BCBSA", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    event = _post_allowlist_change_request_event(direction="INVALID")
    add_jwt_auth(event, "BCBSA")
    resp = vendor_handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "VALIDATION_ERROR"


def _has_db_config() -> bool:
    """True if DATABASE_URL, DB_URL, or DB_SECRET_ARN is set with a valid-looking value.
    Rejects empty, 'None', and invalid placeholders that cause GetSecretValue to fail.
    """

    def _valid_secret_arn(val: str | None) -> bool:
        s = (val or "").strip()
        if not s or s.upper() == "NONE":
            return False
        return s.startswith("arn:aws:secretsmanager:")

    def _valid_db_url(val: str | None) -> bool:
        s = (val or "").strip()
        if not s or s.upper() == "NONE":
            return False
        return s.startswith("postgresql://") or s.startswith("postgres://")

    return (
        _valid_db_url(os.environ.get("DATABASE_URL"))
        or _valid_db_url(os.environ.get("DB_URL"))
        or _valid_secret_arn(os.environ.get("DB_SECRET_ARN"))
    )


@pytest.mark.skipif(
    not _has_db_config(),
    reason="DATABASE_URL, DB_URL, or DB_SECRET_ARN required for integration test",
)
def test_post_allowlist_change_requests_persists_row() -> None:
    """Integration: POST allowlist-change-requests persists to control_plane.allowlist_change_requests."""
    # Lambda uses DB_URL; fallback to DATABASE_URL for local/test
    if not os.environ.get("DB_URL") and os.environ.get("DATABASE_URL"):
        os.environ["DB_URL"] = os.environ["DATABASE_URL"]

    event = _post_allowlist_change_request_event(
        direction="OUTBOUND",
        operation_code="GET_JOKE_DEMO",
        target_vendor_codes=["LH001"],
        request_type="PROVIDER_NARROWING",
    )
    add_jwt_auth(event, "LH001")
    resp = vendor_handler(event, None)

    assert resp["statusCode"] == 201
    body = json.loads(resp["body"])
    req_id = body.get("id")
    assert req_id
    assert body.get("status") == "PENDING"

    import psycopg2
    from psycopg2.extras import RealDictCursor

    db_url = os.environ.get("DATABASE_URL") or os.environ.get("DB_URL")
    if not db_url and os.environ.get("DB_SECRET_ARN"):
        import boto3
        import urllib.parse
        client = boto3.client("secretsmanager")
        raw = json.loads(client.get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"])
        pw_enc = urllib.parse.quote(str(raw.get("password", "")), safe="")
        db_url = (
            f"postgresql://{raw.get('username') or raw.get('user')}:{pw_enc}"
            f"@{raw['host']}:{raw.get('port', 5432)}"
            f"/{raw.get('dbname', raw.get('database', 'integrationhub'))}"
        )

    conn = psycopg2.connect(db_url, connect_timeout=10)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, source_vendor_code, target_vendor_codes, operation_code, direction,
                       request_type, status
                FROM control_plane.allowlist_change_requests
                WHERE id = %s
                """,
                (req_id,),
            )
            row = cur.fetchone()
        assert row is not None, f"Row with id={req_id} not found in allowlist_change_requests"
        assert row["source_vendor_code"] == "LH001"
        assert row["operation_code"] == "GET_JOKE_DEMO"
        assert row["direction"] == "OUTBOUND"
        assert row["request_type"] == "PROVIDER_NARROWING"
        assert row["status"] == "PENDING"
        assert row["target_vendor_codes"] == ["LH001"]
    finally:
        conn.close()


def _registry_change_requests_event(source: str = "allowlist", status: str = "PENDING") -> dict:
    """Build GET /v1/registry/change-requests event."""
    return {
        "path": "/v1/registry/change-requests",
        "rawPath": "/v1/registry/change-requests",
        "httpMethod": "GET",
        "headers": {"Authorization": "Bearer test-admin-jwt"},
        "queryStringParameters": {"source": source, "status": status},
        "pathParameters": {},
        "requestContext": {"http": {"method": "GET"}},
    }


def _add_registry_jwt_auth(event: dict) -> None:
    """Add JWT authorizer so registry_lambda require_admin_secret passes."""
    ctx = event.get("requestContext") or {}
    ctx["authorizer"] = {
        "principalId": "admin",
        "jwt": {"claims": {"sub": "admin-user", "aud": "api://default", "groups": ["admins", "admin"]}},
    }
    event["requestContext"] = ctx


@patch("registry_lambda._get_connection")
def test_registry_list_change_requests_source_allowlist_filters_pending(mock_conn_ctx: MagicMock) -> None:
    """GET /v1/registry/change-requests?source=allowlist&status=PENDING returns only PENDING rows."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    pending_row = {
        "id": _uuid.uuid4(),
        "source_vendor_code": "BCBSA",
        "target_vendor_codes": ["LH001"],
        "use_wildcard_target": False,
        "operation_code": "GET_WEATHER",
        "direction": "OUTBOUND",
        "request_type": "PROVIDER_NARROWING",
        "rule_scope": "vendor",
        "status": "PENDING",
        "requested_by": None,
        "reviewed_by": None,
        "decision_reason": None,
        "created_at": datetime(2026, 2, 25, 12, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 2, 25, 12, 0, tzinfo=timezone.utc),
        "raw_payload": None,
    }
    cursor = MagicMock()
    cursor.fetchall.return_value = [pending_row]
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    from registry_lambda import handler as registry_handler

    event = _registry_change_requests_event(source="allowlist", status="PENDING")
    _add_registry_jwt_auth(event)
    resp = registry_handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    items = body.get("items", [])
    assert len(items) == 1
    assert items[0]["status"] == "PENDING"
    assert items[0]["sourceVendorCode"] == "BCBSA"
    assert items[0]["operationCode"] == "GET_WEATHER"
