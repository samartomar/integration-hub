"""Unit tests for Vendor Registry Lambda - POST /v1/vendor/endpoints/verify."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from vendor_registry_lambda import handler  # noqa: E402
from vendor_registry_jwt import add_jwt_auth  # noqa: E402


def _verify_event(operation_code: str = "GET_WEATHER", flow_direction: str | None = None) -> dict:
    body: dict = {"operationCode": operation_code}
    if flow_direction:
        body["flowDirection"] = flow_direction
    return {
        "path": "/v1/vendor/endpoints/verify",
        "rawPath": "/v1/vendor/endpoints/verify",
        "httpMethod": "POST",
        "pathParameters": {},
        "requestContext": {"http": {"method": "POST"}, "requestId": "test-req-id"},
        "headers": {},
        "body": json.dumps(body),
    }


@patch("vendor_registry_lambda.load_effective_contract_optional")
@patch("vendor_registry_lambda._write_audit_event")
@patch("vendor_registry_lambda._update_endpoint_verification")
@patch("vendor_registry_lambda._make_verification_request")
@patch("vendor_registry_lambda._load_endpoint")
@patch("vendor_registry_lambda._get_connection")
def test_verify_no_auth_endpoint_success_updates_to_verified(
    mock_conn_ctx: MagicMock,
    mock_load: MagicMock,
    mock_verify_http: MagicMock,
    mock_update: MagicMock,
    _mock_audit: MagicMock,
    _mock_load_contract: MagicMock,
) -> None:
    """No-auth endpoint (vendor_auth_profile_id NULL) that verifies successfully is persisted as VERIFIED."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    endpoint_row = {
        "id": "ep-uuid-123",
        "vendor_code": "ACME",
        "operation_code": "GET_WEATHER",
        "flow_direction": "OUTBOUND",
        "url": "https://api.acme.com/weather",
        "http_method": "POST",
        "payload_format": "json",
        "timeout_ms": 8000,
        "is_active": True,
        "vendor_auth_profile_id": None,
        "verification_status": "PENDING",
        "last_verified_at": None,
        "last_verification_error": None,
        "verification_request": None,
    }
    mock_load.return_value = endpoint_row
    mock_verify_http.return_value = (True, 200, '{"temp": 72}')
    _mock_load_contract.return_value = None  # no contract sample needed for simple verify
    cursor = MagicMock()
    cursor.fetchone.return_value = ("ACME", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    event = _verify_event("GET_WEATHER")
    add_jwt_auth(event, "ACME")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body.get("endpoint", {}).get("verificationStatus") == "VERIFIED"
    assert body.get("endpoint", {}).get("endpointHealth") == "healthy"
    assert body.get("endpoint", {}).get("verificationResult", {}).get("status") == "VERIFIED"

    mock_update.assert_called_once()
    call_args, call_kwargs = mock_update.call_args
    assert call_args[0] == mock_conn
    assert call_args[1] == "ep-uuid-123"
    assert call_args[2] == "VERIFIED"
    assert call_args[3] is None
    assert call_kwargs.get("verification_request") is None  # do not overwrite with result


@patch("vendor_registry_lambda._write_audit_event")
@patch("vendor_registry_lambda._update_endpoint_verification")
@patch("vendor_registry_lambda._make_verification_request")
@patch("vendor_registry_lambda._get_auth_profile_for_vendor")
@patch("vendor_registry_lambda._load_endpoint")
@patch("vendor_registry_lambda._get_connection")
def test_verify_endpoint_with_missing_auth_profile_marks_failed(
    mock_conn_ctx: MagicMock,
    mock_load: MagicMock,
    mock_get_profile: MagicMock,
    mock_verify_http: MagicMock,
    mock_update: MagicMock,
    _mock_audit: MagicMock,
) -> None:
    """Endpoint with vendor_auth_profile_id set but profile missing/inactive marks FAILED, does not crash."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    endpoint_row = {
        "id": "ep-uuid-456",
        "vendor_code": "ACME",
        "operation_code": "GET_WEATHER",
        "flow_direction": "INBOUND",
        "url": "https://api.acme.com/weather",
        "http_method": "POST",
        "vendor_auth_profile_id": "profile-missing-uuid",
        "verification_status": "PENDING",
    }
    mock_load.return_value = endpoint_row
    mock_get_profile.return_value = None
    cursor = MagicMock()
    cursor.fetchone.return_value = ("ACME", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    event = _verify_event("GET_WEATHER")
    add_jwt_auth(event, "ACME")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body.get("endpoint", {}).get("verificationStatus") == "FAILED"
    assert body.get("endpoint", {}).get("endpointHealth") == "error"
    assert "Auth profile not found or inactive" in str(
        body.get("endpoint", {}).get("verificationResult", {}).get("responseSnippet", "")
    )

    mock_update.assert_called_once_with(
        mock_conn,
        "ep-uuid-456",
        "FAILED",
        "Auth profile not found or inactive",
        None,
    )
    mock_verify_http.assert_not_called()


@patch("vendor_registry_lambda.load_effective_contract_optional")
@patch("vendor_registry_lambda._write_audit_event")
@patch("vendor_registry_lambda._update_endpoint_verification")
@patch("vendor_registry_lambda._make_verification_request")
@patch("vendor_registry_lambda._load_endpoint")
@patch("vendor_registry_lambda._get_connection")
def test_verify_http_failure_updates_to_failed(
    mock_conn_ctx: MagicMock,
    mock_load: MagicMock,
    mock_verify_http: MagicMock,
    mock_update: MagicMock,
    _mock_audit: MagicMock,
    _mock_load_contract: MagicMock,
) -> None:
    """When HTTP verification fails, status is updated to FAILED with error message."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    endpoint_row = {
        "id": "ep-uuid-789",
        "vendor_code": "FOO",
        "operation_code": "GET_WEATHER",
        "flow_direction": "OUTBOUND",
        "url": "https://api.foo.com/weather",
        "http_method": "POST",
        "vendor_auth_profile_id": None,
        "verification_status": "PENDING",
    }
    mock_load.return_value = endpoint_row
    mock_verify_http.return_value = (False, 500, "Internal Server Error")
    _mock_load_contract.return_value = None
    cursor = MagicMock()
    cursor.fetchone.return_value = ("FOO", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    event = _verify_event("GET_WEATHER")
    add_jwt_auth(event, "FOO")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body.get("endpoint", {}).get("verificationStatus") == "FAILED"
    assert body.get("endpoint", {}).get("verificationResult", {}).get("status") == "FAILED"

    mock_update.assert_called_once()
    call_args = mock_update.call_args[0]
    assert call_args[2] == "FAILED"
    assert "500" in str(call_args[3]) or "Internal" in str(call_args[3])


@patch("vendor_registry_lambda._load_endpoint")
@patch("vendor_registry_lambda._get_connection")
def test_verify_endpoint_not_found_returns_404(
    mock_conn_ctx: MagicMock,
    mock_load: MagicMock,
) -> None:
    """When endpoint does not exist, returns 404."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_load.return_value = None
    cursor = MagicMock()
    cursor.fetchone.return_value = ("BAR", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    event = _verify_event("UNKNOWN_OP")
    add_jwt_auth(event, "BAR")
    resp = handler(event, None)

    assert resp["statusCode"] == 404
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "ENDPOINT_NOT_FOUND"
