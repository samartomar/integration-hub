"""Unit tests for Vendor Registry Lambda - POST /v1/vendor/supported-operations ON CONFLICT behavior."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from vendor_registry_lambda import _upsert_supported_operation, handler  # noqa: E402


def _post_supported_ops_event(
    operation_code: str = "GET_WEATHER",
    canonical_version: str | None = None,
    flow_direction: str | None = None,
    supports_outbound: bool | None = None,
    supports_inbound: bool | None = None,
) -> dict:
    body = {"operationCode": operation_code}
    if canonical_version is not None:
        body["canonicalVersion"] = canonical_version
    if flow_direction is not None:
        body["flowDirection"] = flow_direction
    if supports_outbound is not None:
        body["supportsOutbound"] = supports_outbound
    if supports_inbound is not None:
        body["supportsInbound"] = supports_inbound
    return {
        "path": "/v1/vendor/supported-operations",
        "rawPath": "/v1/vendor/supported-operations",
        "httpMethod": "POST",
        "pathParameters": {},
        "requestContext": {"http": {"method": "POST"}, "requestId": "test-req-id"},
        "headers": {"Authorization": "Bearer test-key"},
        "body": json.dumps(body),
    }


@patch("vendor_registry_lambda._execute_one")
@patch("vendor_registry_lambda._write_audit_event")
@patch("vendor_registry_lambda._get_connection")
def test_upsert_supported_operation_includes_canonical_version_and_flow_direction(
    mock_conn_ctx: MagicMock,
    mock_audit: MagicMock,
    mock_execute: MagicMock,
) -> None:
    """_upsert_supported_operation passes canonical_version and flow_direction to INSERT/ON CONFLICT."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_execute.return_value = {
        "id": "uuid-1",
        "vendor_code": "ACME",
        "operation_code": "GET_WEATHER",
        "is_active": True,
        "created_at": "2024-01-01",
        "updated_at": "2024-01-02",
        "supports_outbound": True,
        "supports_inbound": True,
    }

    _upsert_supported_operation(
        mock_conn, "ACME", "GET_WEATHER", True, "req-1",
        canonical_version="v1", flow_direction="INBOUND",
    )

    mock_execute.assert_called_once()
    call_args = mock_execute.call_args
    params = call_args[0][2]
    assert params[4] == "v1"
    assert params[5] == "INBOUND"


@patch("vendor_registry_lambda._execute_one")
@patch("vendor_registry_lambda._write_audit_event")
@patch("vendor_registry_lambda._get_connection")
def test_upsert_supported_operation_same_keys_twice_updates(
    mock_conn_ctx: MagicMock,
    mock_audit: MagicMock,
    mock_execute: MagicMock,
) -> None:
    """Insert same (vendor, op, canonical_version, flow_direction) twice: ON CONFLICT updates, returns one row."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    row1 = {
        "id": "uuid-1",
        "vendor_code": "ACME",
        "operation_code": "GET_WEATHER",
        "is_active": True,
        "created_at": "2024-01-01",
        "updated_at": "2024-01-01",
        "supports_outbound": True,
        "supports_inbound": True,
    }
    row2 = {
        "id": "uuid-1",
        "vendor_code": "ACME",
        "operation_code": "GET_WEATHER",
        "is_active": True,
        "created_at": "2024-01-01",
        "updated_at": "2024-01-02",
        "supports_outbound": False,
        "supports_inbound": True,
    }
    mock_execute.side_effect = [row1, row2]

    r1 = _upsert_supported_operation(
        mock_conn, "ACME", "GET_WEATHER", True, "req-1",
        supports_outbound=True, supports_inbound=True,
    )
    r2 = _upsert_supported_operation(
        mock_conn, "ACME", "GET_WEATHER", True, "req-2",
        supports_outbound=False, supports_inbound=True,
    )

    assert r1["supports_outbound"] is True
    assert r2["supports_outbound"] is False
    assert mock_execute.call_count == 2
    assert r1["id"] == r2["id"]


@patch("vendor_registry_lambda._update_supported_operation_is_active")
@patch("vendor_registry_lambda._execute_one")
@patch("vendor_registry_lambda._write_audit_event")
@patch("vendor_registry_lambda._get_connection")
def test_upsert_supported_operation_is_active_false_deactivates(
    mock_conn_ctx: MagicMock,
    mock_audit: MagicMock,
    mock_execute: MagicMock,
    mock_update: MagicMock,
) -> None:
    """Insert with is_active=false deactivates existing row via _update_supported_operation_is_active."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_update.return_value = {
        "id": "uuid-1",
        "vendor_code": "ACME",
        "operation_code": "GET_WEATHER",
        "is_active": False,
        "created_at": "2024-01-01",
        "updated_at": "2024-01-02",
        "supports_outbound": True,
        "supports_inbound": True,
    }

    r = _upsert_supported_operation(
        mock_conn, "ACME", "GET_WEATHER", False, "req-1",
    )

    assert r["is_active"] is False
    mock_update.assert_called_once_with(mock_conn, "ACME", "GET_WEATHER", False)
    mock_execute.assert_not_called()
