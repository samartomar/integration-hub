"""Unit tests for Vendor Registry Lambda - PATCH and DELETE /v1/vendor/operations/{operationCode}."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from vendor_registry_lambda import handler  # noqa: E402
from vendor_registry_jwt import add_jwt_auth  # noqa: E402


def _patch_event(operation_code: str, is_active: bool, headers: dict | None = None) -> dict:
    return {
        "path": f"/v1/vendor/operations/{operation_code}",
        "rawPath": f"/v1/vendor/operations/{operation_code}",
        "httpMethod": "PATCH",
        "pathParameters": {},
        "requestContext": {"http": {"method": "PATCH"}, "requestId": "test-req-id"},
        "headers": headers or {},
        "body": json.dumps({"isActive": is_active}),
    }


def _delete_event(operation_code: str, headers: dict | None = None) -> dict:
    return {
        "path": f"/v1/vendor/operations/{operation_code}",
        "rawPath": f"/v1/vendor/operations/{operation_code}",
        "httpMethod": "DELETE",
        "pathParameters": {},
        "requestContext": {"http": {"method": "DELETE"}, "requestId": "test-req-id"},
        "headers": headers or {},
        "body": None,
    }


@patch("vendor_registry_lambda._update_supported_operation_is_active")
@patch("vendor_registry_lambda._get_connection")
def test_patch_operations_sets_is_active_true(
    mock_conn_ctx: MagicMock,
    mock_update: MagicMock,
) -> None:
    """PATCH with isActive: true updates and returns the row."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    mock_update.return_value = {
        "id": "uuid-1",
        "vendor_code": "LH001",
        "operation_code": "GET_RECEIPT",
        "is_active": True,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
    }

    event = _patch_event("GET_RECEIPT", True)
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body.get("item", {}).get("operationCode") == "GET_RECEIPT"
    assert body.get("item", {}).get("isActive") is True
    mock_update.assert_called_once_with(mock_conn, "LH001", "GET_RECEIPT", True)


@patch("vendor_registry_lambda._update_supported_operation_is_active")
@patch("vendor_registry_lambda._get_connection")
def test_patch_operations_sets_is_active_false(
    mock_conn_ctx: MagicMock,
    mock_update: MagicMock,
) -> None:
    """PATCH with isActive: false updates and returns the row."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    mock_update.return_value = {
        "id": "uuid-1",
        "vendor_code": "LH001",
        "operation_code": "GET_RECEIPT",
        "is_active": False,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
    }

    event = _patch_event("GET_RECEIPT", False)
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body.get("item", {}).get("isActive") is False
    mock_update.assert_called_once_with(mock_conn, "LH001", "GET_RECEIPT", False)


@patch("vendor_registry_lambda._update_supported_operation_is_active")
@patch("vendor_registry_lambda._get_connection")
def test_patch_operations_not_found_returns_404(
    mock_conn_ctx: MagicMock,
    mock_update: MagicMock,
) -> None:
    """PATCH when operation not in vendor config returns 404 VENDOR_OPERATION_NOT_FOUND."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    mock_update.return_value = None

    event = _patch_event("UNKNOWN_OP", True)
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 404
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "VENDOR_OPERATION_NOT_FOUND"


@patch("vendor_registry_lambda._delete_vendor_operation_cascade")
@patch("vendor_registry_lambda._get_connection")
def test_delete_operations_success_returns_200(
    mock_conn_ctx: MagicMock,
    mock_delete_cascade: MagicMock,
) -> None:
    """DELETE when operation exists returns 200 with operationCode."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    mock_delete_cascade.return_value = True

    event = _delete_event("GET_RECEIPT")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body.get("operationCode") == "GET_RECEIPT"
    mock_delete_cascade.assert_called_once_with(mock_conn, "LH001", "GET_RECEIPT")


@patch("vendor_registry_lambda._delete_vendor_operation_cascade")
@patch("vendor_registry_lambda._get_connection")
def test_delete_operations_not_found_returns_404(
    mock_conn_ctx: MagicMock,
    mock_delete_cascade: MagicMock,
) -> None:
    """DELETE when operation not configured for vendor returns 404."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    mock_delete_cascade.return_value = False

    event = _delete_event("UNKNOWN_OP")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 404
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "VENDOR_OPERATION_NOT_FOUND"


@patch("vendor_registry_lambda._delete_vendor_operation_cascade")
@patch("vendor_registry_lambda._get_connection")
def test_delete_operations_idempotent_second_call_returns_404(
    mock_conn_ctx: MagicMock,
    mock_delete_cascade: MagicMock,
) -> None:
    """DELETE called twice: first succeeds, second returns 404 (idempotent - no row to delete)."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH001", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor

    mock_delete_cascade.side_effect = [True, False]  # first: deleted, second: nothing to delete

    event = _delete_event("GET_RECEIPT")
    add_jwt_auth(event, "LH001")
    resp1 = handler(event, None)
    add_jwt_auth(event, "LH001")
    resp2 = handler(event, None)

    assert resp1["statusCode"] == 200
    assert resp2["statusCode"] == 404
    assert mock_delete_cascade.call_count == 2
