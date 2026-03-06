"""Unit tests for Vendor Registry Lambda - POST /v1/vendor/endpoints (direct persist, no change-request)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from vendor_registry_lambda import handler  # noqa: E402
from vendor_registry_jwt import add_jwt_auth  # noqa: E402


def _post_endpoint_event(
    operation_code: str = "GET_RECEIPT",
    url: str = "https://api.example.com/receipt",
    http_method: str = "POST",
    payload_format: str = "JSON",
    timeout_ms: int = 8000,
    is_active: bool = True,
    headers: dict | None = None,
) -> dict:
    body = {
        "operationCode": operation_code,
        "url": url,
        "httpMethod": http_method,
        "payloadFormat": payload_format,
        "timeoutMs": timeout_ms,
        "isActive": is_active,
    }
    return {
        "path": "/v1/vendor/endpoints",
        "rawPath": "/v1/vendor/endpoints",
        "httpMethod": "POST",
        "pathParameters": {},
        "requestContext": {"http": {"method": "POST"}, "requestId": "test-req-id"},
        "headers": headers or {},
        "body": json.dumps(body),
    }


@patch("vendor_registry_lambda.is_feature_gated", return_value=False)
@patch("vendor_registry_lambda._write_audit_event")
@patch("vendor_registry_lambda._upsert_endpoint")
@patch("vendor_registry_lambda._get_connection")
def test_post_vendor_endpoint_creates_row_directly(
    mock_conn_ctx: MagicMock,
    mock_upsert: MagicMock,
    _mock_audit: MagicMock,
    _mock_gated: MagicMock,
) -> None:
    """POST /v1/vendor/endpoints directly persists to vendor_endpoints, returns 200 with endpoint object."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    mock_upsert.return_value = {
        "id": "ep-uuid-123",
        "vendor_code": "LH001",
        "operation_code": "GET_RECEIPT",
        "flow_direction": "OUTBOUND",
        "url": "https://api.example.com/receipt",
        "http_method": "POST",
        "payload_format": "JSON",
        "timeout_ms": 8000,
        "is_active": True,
        "verification_status": "PENDING",
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-15T10:00:00Z",
    }

    event = _post_endpoint_event()
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "endpoint" in body
    ep = body["endpoint"]
    assert ep.get("id") == "ep-uuid-123"
    assert ep.get("operationCode") == "GET_RECEIPT"
    assert ep.get("url") == "https://api.example.com/receipt"
    assert ep.get("verificationStatus") == "PENDING"
    assert ep.get("endpointHealth") in ("healthy", "not_verified", "error")

    mock_upsert.assert_called_once()
    call_kwargs = mock_upsert.call_args[1]
    assert call_kwargs["vendor_code"] == "LH001"
    assert call_kwargs["operation_code"] == "GET_RECEIPT"
    assert call_kwargs["url"] == "https://api.example.com/receipt"
    assert call_kwargs["flow_direction"] == "OUTBOUND"


@patch("vendor_registry_lambda.is_feature_gated", return_value=False)
@patch("vendor_registry_lambda._create_vendor_change_request")
@patch("vendor_registry_lambda._write_audit_event")
@patch("vendor_registry_lambda._upsert_endpoint")
@patch("vendor_registry_lambda._get_connection")
def test_post_vendor_endpoint_does_not_create_change_request(
    mock_conn_ctx: MagicMock,
    mock_upsert: MagicMock,
    _mock_audit: MagicMock,
    mock_create_cr: MagicMock,
    _mock_gated: MagicMock,
) -> None:
    """POST /v1/vendor/endpoints does NOT create any change-request row."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    mock_upsert.return_value = {
        "id": "ep-uuid-456",
        "vendor_code": "LH001",
        "operation_code": "GET_WEATHER",
        "flow_direction": "OUTBOUND",
        "url": "https://api.example.com/weather",
        "verification_status": "PENDING",
    }

    event = _post_endpoint_event(operation_code="GET_WEATHER", url="https://api.example.com/weather")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "status" not in body or body.get("status") != "PENDING"
    assert "changeRequestId" not in body

    mock_create_cr.assert_not_called()


@patch("vendor_registry_lambda.is_feature_gated", return_value=False)
@patch("vendor_registry_lambda._write_audit_event")
@patch("vendor_registry_lambda._upsert_endpoint")
@patch("vendor_registry_lambda._get_connection")
def test_post_vendor_endpoint_updates_existing(
    mock_conn_ctx: MagicMock,
    mock_upsert: MagicMock,
    _mock_audit: MagicMock,
    _mock_gated: MagicMock,
) -> None:
    """POST /v1/vendor/endpoints with changed url updates existing row (ON CONFLICT)."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH002", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    mock_upsert.return_value = {
        "id": "ep-existing",
        "vendor_code": "LH002",
        "operation_code": "GET_RECEIPT",
        "url": "https://api.v2.com/receipt",
        "timeout_ms": 5000,
        "updated_at": "2024-01-15T11:00:00Z",
    }

    event = _post_endpoint_event(
        url="https://api.v2.com/receipt",
        timeout_ms=5000,
    )
    event["body"] = json.dumps({
        "operationCode": "GET_RECEIPT",
        "url": "https://api.v2.com/receipt",
        "timeoutMs": 5000,
    })
    add_jwt_auth(event, "LH002")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    mock_upsert.assert_called_once()
    call_kwargs = mock_upsert.call_args[1]
    assert call_kwargs["url"] == "https://api.v2.com/receipt"
    assert call_kwargs["timeout_ms"] == 5000


def test_post_vendor_endpoint_missing_operation_code_400() -> None:
    """POST /v1/vendor/endpoints without operationCode returns 400."""
    with patch("vendor_registry_lambda._get_connection") as mock_ctx:
        mock_conn = MagicMock()
        mock_ctx.return_value.__enter__.return_value = mock_conn
        cursor = MagicMock()
        cursor.fetchone.return_value = ("LH001", True)
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = cursor

        event = _post_endpoint_event()
        event["body"] = json.dumps({"url": "https://example.com"})
        add_jwt_auth(event, "LH001")

        resp = handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "VALIDATION_ERROR"
    assert "operationcode" in body["error"]["message"].lower() or "required" in body["error"]["message"].lower()


def test_post_vendor_endpoint_missing_url_400() -> None:
    """POST /v1/vendor/endpoints without url returns 400."""
    with patch("vendor_registry_lambda._get_connection") as mock_ctx:
        mock_conn = MagicMock()
        mock_ctx.return_value.__enter__.return_value = mock_conn
        cursor = MagicMock()
        cursor.fetchone.return_value = ("LH001", True)
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = cursor

        event = _post_endpoint_event()
        event["body"] = json.dumps({"operationCode": "GET_RECEIPT"})
        add_jwt_auth(event, "LH001")

        resp = handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "VALIDATION_ERROR"
