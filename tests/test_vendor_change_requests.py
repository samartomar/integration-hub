"""Unit tests for vendor change requests approval flow."""

from __future__ import annotations

import json
from datetime import datetime, timezone
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from vendor_registry_lambda import handler as vendor_handler  # noqa: E402
from vendor_registry_jwt import add_jwt_auth  # noqa: E402


def _post_change_request_event(
    request_type: str = "ALLOWLIST_RULE",
    payload: dict | None = None,
    target_vendor_code: str | None = None,
    operation_code: str | None = None,
    flow_direction: str | None = None,
) -> dict:
    body: dict = {"requestType": request_type, "payload": payload or {}}
    if target_vendor_code:
        body["targetVendorCode"] = target_vendor_code
    if operation_code:
        body["operationCode"] = operation_code
    if flow_direction:
        body["flowDirection"] = flow_direction
    return {
        "path": "/v1/vendor/change-requests",
        "rawPath": "/v1/vendor/change-requests",
        "httpMethod": "POST",
        "pathParameters": {},
        "requestContext": {"http": {"method": "POST"}, "requestId": "test-req-id"},
        "headers": {},
        "body": json.dumps(body),
    }


def _get_change_requests_event(status: str = "PENDING", limit: int | None = None) -> dict:
    params: dict = {}
    if status:
        params["status"] = status
    if limit is not None:
        params["limit"] = str(limit)
    return {
        "path": "/v1/vendor/change-requests",
        "rawPath": "/v1/vendor/change-requests",
        "httpMethod": "GET",
        "pathParameters": {},
        "queryStringParameters": params or {},
        "requestContext": {"http": {"method": "GET"}, "requestId": "test-req-id"},
        "headers": {},
    }


@patch("vendor_registry_lambda.is_feature_gated", return_value=True)
@patch("vendor_registry_lambda._get_connection")
def test_post_change_request_allowlist_201(
    mock_conn_ctx: MagicMock,
    _mock_gated: MagicMock,
) -> None:
    """POST /v1/vendor/change-requests with ALLOWLIST_RULE returns 201."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        ("LH001", True),  # vendor validation
        {
            "id": "cr-uuid-1",
            "requesting_vendor_code": "LH001",
            "request_type": "ALLOWLIST_RULE",
            "status": "PENDING",
            "created_at": datetime(2026, 2, 24, 12, 0, 0, tzinfo=timezone.utc),
        },
    ]
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    payload = {
        "sourceVendorCode": "LH001",
        "targetVendorCode": "LH002",
        "operationCode": "GET_WEATHER",
        "flowDirection": "OUTBOUND",
    }
    event = _post_change_request_event(
        request_type="ALLOWLIST_RULE",
        payload=payload,
        operation_code="GET_WEATHER",
        target_vendor_code="LH002",
        flow_direction="OUTBOUND",
    )
    add_jwt_auth(event, "LH001")
    resp = vendor_handler(event, None)

    assert resp["statusCode"] == 201
    body = json.loads(resp["body"])
    assert body.get("id") == "cr-uuid-1"
    assert body.get("status") == "PENDING"
    assert body.get("requestType") == "ALLOWLIST_RULE"
    assert "summary" in body


@patch("vendor_registry_lambda._get_connection")
def test_post_change_request_invalid_type_400(
    mock_conn_ctx: MagicMock,
) -> None:
    """POST /v1/vendor/change-requests with invalid requestType returns 400."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    event = _post_change_request_event(
        request_type="INVALID_TYPE",
        payload={"foo": "bar"},
    )
    add_jwt_auth(event, "LH001")
    resp = vendor_handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "VALIDATION_ERROR"
    assert "requestType" in body["error"]["message"]


@patch("vendor_registry_lambda._get_connection")
def test_get_change_requests_200(
    mock_conn_ctx: MagicMock,
) -> None:
    """GET /v1/vendor/change-requests returns vendor's pending requests."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    cursor = MagicMock()
    ts = datetime(2026, 2, 24, 12, 0, 0, tzinfo=timezone.utc)
    cursor.fetchall.return_value = [
        {
            "id": "cr-1",
            "requesting_vendor_code": "LH001",
            "target_vendor_code": "LH002",
            "request_type": "ALLOWLIST_RULE",
            "operation_code": "GET_WEATHER",
            "flow_direction": "OUTBOUND",
            "payload": {},
            "summary": {"title": "Allow outbound GET_WEATHER to LH002"},
            "status": "PENDING",
            "created_at": ts,
            "updated_at": ts,
        },
    ]
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.fetchone.return_value = ("LH001", True)
    mock_conn.cursor.return_value = cursor

    event = _get_change_requests_event(status="PENDING")
    add_jwt_auth(event, "LH001")
    resp = vendor_handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    items = body.get("items", [])
    assert len(items) == 1
    assert items[0]["requestType"] == "ALLOWLIST_RULE"
    assert items[0]["status"] == "PENDING"
    assert items[0]["requestingVendorCode"] == "LH001"


def _post_my_allowlist_change_request_event(
    direction: str = "OUTBOUND",
    operation_code: str = "GET_WEATHER",
    target_vendor_codes: list[str] | None = None,
    use_wildcard_target: bool = False,
) -> dict:
    body: dict = {
        "direction": direction,
        "operationCode": operation_code,
        "targetVendorCodes": target_vendor_codes or [],
        "useWildcardTarget": use_wildcard_target,
    }
    return {
        "path": "/v1/vendor/my-allowlist/change-request",
        "rawPath": "/v1/vendor/my-allowlist/change-request",
        "httpMethod": "POST",
        "pathParameters": {},
        "requestContext": {"http": {"method": "POST"}, "requestId": "test-req-id"},
        "headers": {},
        "body": json.dumps(body),
    }


@patch("vendor_registry_lambda._get_connection")
def test_post_my_allowlist_change_request_happy_path(
    mock_conn_ctx: MagicMock,
) -> None:
    """POST /v1/vendor/my-allowlist/change-request with valid body returns 201."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        ("LH001", True),  # vendor validation
        {
            "id": "cr-uuid-allowlist",
            "requesting_vendor_code": "LH001",
            "request_type": "ALLOWLIST_RULE",
            "status": "PENDING",
            "created_at": datetime(2026, 2, 24, 12, 0, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 2, 24, 12, 0, 0, tzinfo=timezone.utc),
        },
    ]
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    event = _post_my_allowlist_change_request_event(
        direction="OUTBOUND",
        operation_code="GET_WEATHER",
        target_vendor_codes=["LH002"],
    )
    add_jwt_auth(event, "LH001")
    resp = vendor_handler(event, None)

    assert resp["statusCode"] == 201
    body = json.loads(resp["body"])
    assert body.get("id") == "cr-uuid-allowlist"
    assert body.get("status") == "PENDING"
    assert body.get("requestType") == "ALLOWLIST_RULE"
    assert "summary" in body
    assert body["summary"].get("title") == "Allow LH001 to call LH002 on GET_WEATHER (OUTBOUND)"


@patch("vendor_registry_lambda._get_connection")
def test_post_my_allowlist_change_request_missing_operation_code_400(
    mock_conn_ctx: MagicMock,
) -> None:
    """POST /v1/vendor/my-allowlist/change-request without operationCode returns 400."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    event = _post_my_allowlist_change_request_event(
        direction="OUTBOUND",
        operation_code="",
        target_vendor_codes=["LH002"],
    )
    event["body"] = json.dumps({
        "direction": "OUTBOUND",
        "targetVendorCodes": ["LH002"],
        "useWildcardTarget": False,
    })
    add_jwt_auth(event, "LH001")
    resp = vendor_handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "VALIDATION_ERROR"
    assert "operationcode" in body["error"]["message"].lower()


@patch("vendor_registry_lambda._get_connection")
def test_post_my_allowlist_change_request_invalid_direction_400(
    mock_conn_ctx: MagicMock,
) -> None:
    """POST /v1/vendor/my-allowlist/change-request with invalid direction returns 400."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    event = _post_my_allowlist_change_request_event(
        direction="OUTBOUND",
        operation_code="GET_WEATHER",
        target_vendor_codes=["LH002"],
    )
    event["body"] = json.dumps({
        "direction": "INVALID",
        "operationCode": "GET_WEATHER",
        "targetVendorCodes": ["LH002"],
        "useWildcardTarget": False,
    })
    add_jwt_auth(event, "LH001")
    resp = vendor_handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "VALIDATION_ERROR"
    assert "direction" in body["error"]["message"].lower()
