"""Unit tests for vendor_registry provider narrowing (GET/PUT)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from vendor_registry_lambda import handler  # noqa: E402
from vendor_registry_jwt import add_jwt_auth  # noqa: E402


def _provider_narrowing_get_event(operation_code: str = "GET_WEATHER") -> dict:
    return {
        "path": f"/v1/vendor/provider-narrowing",
        "rawPath": "/v1/vendor/provider-narrowing",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {"operationCode": operation_code},
        "pathParameters": {},
        "requestContext": {"http": {"method": "GET"}},
        "body": None,
    }


def _provider_narrowing_put_event(operation_code: str = "GET_WEATHER", caller_vendor_codes: list[str] | None = None) -> dict:
    body = {"operationCode": operation_code, "callerVendorCodes": caller_vendor_codes or []}
    return {
        "path": "/v1/vendor/provider-narrowing",
        "rawPath": "/v1/vendor/provider-narrowing",
        "httpMethod": "PUT",
        "headers": {"content-type": "application/json", "Authorization": "Bearer key-lh001"},
        "queryStringParameters": None,
        "pathParameters": {},
        "requestContext": {"http": {"method": "PUT"}},
        "body": json.dumps(body),
    }


@patch("vendor_registry_lambda._get_connection")
def test_get_provider_narrowing_returns_admin_envelope_and_vendor_whitelist(
    mock_conn_ctx: MagicMock,
) -> None:
    """GET provider-narrowing returns adminEnvelope and vendorWhitelist for PROVIDER_RECEIVES_ONLY op."""
    mock_conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.side_effect = [("LH001", True), {"direction_policy": "PROVIDER_RECEIVES_ONLY"}]
    cursor.fetchall.side_effect = [
        [{"source_vendor_code": "LH002", "is_any_source": False}, {"source_vendor_code": "LH003", "is_any_source": False}],
        [{"source_vendor_code": "LH002"}],
    ]
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    event = _provider_narrowing_get_event()
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body.get("operationCode") == "GET_WEATHER"
    assert "adminEnvelope" in body
    assert "vendorWhitelist" in body
    assert "LH002" in body["adminEnvelope"]
    assert "LH003" in body["adminEnvelope"]
    assert body["vendorWhitelist"] == ["LH002"]


@patch("vendor_registry_lambda._get_connection")
def test_get_provider_narrowing_not_provider_receives_only_returns_400(
    mock_conn_ctx: MagicMock,
) -> None:
    """GET provider-narrowing for TWO_WAY op returns 400 VALIDATION_ERROR."""
    mock_conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.side_effect = [("LH001", True), {"direction_policy": "TWO_WAY"}]
    mock_conn.cursor.return_value.__enter__.return_value = cursor
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    event = _provider_narrowing_get_event()
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "VALIDATION_ERROR"


@patch("vendor_registry_lambda._get_connection")
def test_put_provider_narrowing_rejects_widening(
    mock_conn_ctx: MagicMock,
) -> None:
    """PUT with caller not in admin envelope returns 400 (cannot widen)."""
    mock_conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        ("LH001", True),
        {"direction_policy": "PROVIDER_RECEIVES_ONLY"},
        None,
    ]
    cursor.fetchall.return_value = [{"source_vendor_code": "LH002", "is_any_source": False}]
    mock_conn.cursor.return_value.__enter__.return_value = cursor
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    event = _provider_narrowing_put_event(caller_vendor_codes=["LH002", "LH999"])
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert "admin envelope" in body.get("error", {}).get("message", "").lower()


@patch("vendor_registry_lambda._get_connection")
def test_put_provider_narrowing_empty_list_deletes_rules(
    mock_conn_ctx: MagicMock,
) -> None:
    """PUT with empty callerVendorCodes deletes vendor rules (no narrowing)."""
    mock_conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        ("LH001", True),
        {"direction_policy": "PROVIDER_RECEIVES_ONLY"},
        None,
    ]
    cursor.fetchall.return_value = [{"source_vendor_code": "LH002", "is_any_source": False}]
    mock_conn.cursor.return_value.__enter__.return_value = cursor
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    event = _provider_narrowing_put_event(caller_vendor_codes=[])
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body.get("operationCode") == "GET_WEATHER"
    assert body.get("callerVendorCodes") == []
