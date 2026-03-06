"""Unit tests for Vendor Registry Lambda - mapping direction validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from vendor_registry_lambda import handler  # noqa: E402
from vendor_registry_jwt import add_jwt_auth  # noqa: E402


def _mapping_event(
    operation_code: str = "GET_RECEIPT",
    canonical_version: str = "v1",
    direction: str = "TO_CANONICAL",
    mapping: dict | None = None,
    headers: dict | None = None,
) -> dict:
    body = {
        "operationCode": operation_code,
        "canonicalVersion": canonical_version,
        "direction": direction,
        "mapping": mapping or {"result": "$.result"},
    }
    return {
        "path": "/v1/vendor/mappings",
        "rawPath": "/v1/vendor/mappings",
        "httpMethod": "POST",
        "pathParameters": {},
        "requestContext": {"http": {"method": "POST"}, "requestId": "test-req-id"},
        "headers": headers or {},
        "body": json.dumps(body),
    }


@patch("vendor_registry_lambda._create_vendor_change_request")
@patch("vendor_registry_lambda._get_connection")
def test_create_mapping_to_canonical_response_passes(
    mock_conn_ctx: MagicMock,
    mock_create_request: MagicMock,
) -> None:
    """Creating mapping creates change request (202)."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    mock_create_request.return_value = {
        "id": "uuid-1",
        "status": "PENDING",
    }

    event = _mapping_event(direction="TO_CANONICAL_RESPONSE")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 202
    body = json.loads(resp["body"])
    assert body.get("status") == "PENDING"
    assert body.get("id") == "uuid-1"
    mock_create_request.assert_called_once()
    call_kwargs = mock_create_request.call_args[1]
    assert call_kwargs["request_type"] == "MAPPING_CONFIG"
    assert call_kwargs["operation_code"] == "GET_RECEIPT"


@patch("vendor_registry_lambda._create_vendor_change_request")
@patch("vendor_registry_lambda._get_connection")
def test_create_mapping_from_canonical_response_passes(
    mock_conn_ctx: MagicMock,
    mock_create_request: MagicMock,
) -> None:
    """Creating mapping with FROM_CANONICAL_RESPONSE creates change request (202)."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    mock_create_request.return_value = {"id": "uuid-2", "status": "PENDING"}

    event = _mapping_event(direction="FROM_CANONICAL_RESPONSE")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 202
    body = json.loads(resp["body"])
    assert body.get("status") == "PENDING"
    mock_create_request.assert_called_once()


@patch("vendor_registry_lambda._get_connection")
def test_create_mapping_invalid_direction_fails(
    mock_conn_ctx: MagicMock,
) -> None:
    """Creating mapping with invalid direction returns VALIDATION_ERROR 400."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    event = _mapping_event(direction="INVALID_DIRECTION")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "VALIDATION_ERROR"
    assert "direction" in body["error"]["message"].lower()


# --- Vendor ownership: LH001 key cannot modify LH002 ---


@patch("vendor_registry_lambda._upsert_endpoint")
@patch("vendor_registry_lambda._get_connection")
def test_lh001_key_cannot_modify_lh002_endpoint(
    mock_conn_ctx: MagicMock,
    mock_upsert: MagicMock,
) -> None:
    """Vendor JWT for LH001 cannot create/modify endpoint for LH002: 403 FORBIDDEN."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    body = {
        "vendorCode": "LH002",
        "operationCode": "GET_RECEIPT",
        "url": "https://example.com/receipt",
    }
    event = {
        "path": "/v1/vendor/endpoints",
        "rawPath": "/v1/vendor/endpoints",
        "httpMethod": "POST",
        "pathParameters": {},
        "requestContext": {"http": {"method": "POST"}, "requestId": "test-req-id"},
        "headers": {},
        "body": json.dumps(body),
    }
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 403
    body_resp = json.loads(resp["body"])
    assert body_resp.get("error", {}).get("code") == "FORBIDDEN"
    assert "another vendor" in body_resp["error"]["message"].lower()
    mock_upsert.assert_not_called()


@patch("vendor_registry_lambda._create_vendor_change_request")
@patch("vendor_registry_lambda._get_connection")
def test_lh001_key_cannot_modify_lh002_mapping(
    mock_conn_ctx: MagicMock,
    mock_create_request: MagicMock,
) -> None:
    """Vendor JWT for LH001 cannot create/modify mapping for LH002: 403 FORBIDDEN."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    body = {
        "vendorCode": "LH002",
        "operationCode": "GET_RECEIPT",
        "canonicalVersion": "v1",
        "direction": "TO_CANONICAL",
        "mapping": {"result": "$.result"},
    }
    event = _mapping_event(mapping={"result": "$.result"})
    event["body"] = json.dumps(body)
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 403
    body_resp = json.loads(resp["body"])
    assert body_resp.get("error", {}).get("code") == "FORBIDDEN"
    assert "another vendor" in body_resp["error"]["message"].lower()
    mock_create_request.assert_not_called()


@patch("vendor_registry_lambda._upsert_contract")
@patch("vendor_registry_lambda._get_connection")
def test_lh001_key_cannot_modify_lh002_contract(
    mock_conn_ctx: MagicMock,
    mock_upsert: MagicMock,
) -> None:
    """Vendor JWT for LH001 cannot create/modify contract for LH002: 403 FORBIDDEN."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    body = {
        "vendorCode": "LH002",
        "operationCode": "GET_RECEIPT",
        "canonicalVersion": "v1",
        "requestSchema": {"type": "object"},
    }
    event = {
        "path": "/v1/vendor/contracts",
        "rawPath": "/v1/vendor/contracts",
        "httpMethod": "POST",
        "pathParameters": {},
        "requestContext": {"http": {"method": "POST"}, "requestId": "test-req-id"},
        "headers": {},
        "body": json.dumps(body),
    }
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 403
    body_resp = json.loads(resp["body"])
    assert body_resp.get("error", {}).get("code") == "FORBIDDEN"
    assert "another vendor" in body_resp["error"]["message"].lower()
    mock_upsert.assert_not_called()


@patch("vendor_registry_lambda._upsert_supported_operation")
@patch("vendor_registry_lambda._get_connection")
def test_lh001_key_cannot_modify_lh002_supported_operation(
    mock_conn_ctx: MagicMock,
    mock_upsert: MagicMock,
) -> None:
    """Vendor JWT for LH001 cannot add supported operation for LH002: 403 FORBIDDEN."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    body = {"vendorCode": "LH002", "operationCode": "GET_RECEIPT"}
    event = {
        "path": "/v1/vendor/supported-operations",
        "rawPath": "/v1/vendor/supported-operations",
        "httpMethod": "POST",
        "pathParameters": {},
        "requestContext": {"http": {"method": "POST"}, "requestId": "test-req-id"},
        "headers": {},
        "body": json.dumps(body),
    }
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 403
    body_resp = json.loads(resp["body"])
    assert body_resp.get("error", {}).get("code") == "FORBIDDEN"
    assert "another vendor" in body_resp["error"]["message"].lower()
    mock_upsert.assert_not_called()
