"""Unit tests for GET /v1/vendor/config-bundle."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from vendor_registry_lambda import handler, _handle_get_config_bundle  # noqa: E402
from vendor_registry_jwt import add_jwt_auth  # noqa: E402


def _config_bundle_event(headers: dict | None = None) -> dict:
    return {
        "path": "/v1/vendor/config-bundle",
        "rawPath": "/v1/vendor/config-bundle",
        "httpMethod": "GET",
        "pathParameters": {},
        "queryStringParameters": {},
        "requestContext": {"http": {"method": "GET"}, "requestId": "test-req-id"},
        "headers": headers or {},
    }


@patch("vendor_registry_lambda._handle_get_my_operations")
@patch("vendor_registry_lambda._handle_get_my_allowlist")
@patch("vendor_registry_lambda._list_mappings")
@patch("vendor_registry_lambda._list_endpoints")
@patch("vendor_registry_lambda._list_supported_operations")
@patch("vendor_registry_lambda._list_operations_catalog")
@patch("vendor_registry_lambda._list_effective_vendor_contracts")
@patch("vendor_registry_lambda._get_connection")
def test_get_config_bundle_returns_all_slices(
    mock_conn: MagicMock,
    mock_list_effective_contracts: MagicMock,
    mock_list_catalog: MagicMock,
    mock_list_supported: MagicMock,
    mock_list_endpoints: MagicMock,
    mock_list_mappings: MagicMock,
    mock_my_allowlist: MagicMock,
    mock_my_operations: MagicMock,
) -> None:
    """GET /v1/vendor/config-bundle returns all sections with vendorCode set."""
    mock_conn_inst = MagicMock()
    mock_conn.return_value.__enter__.return_value = mock_conn_inst
    mock_conn.return_value.__exit__.return_value = False
    cursor = MagicMock()
    cursor.fetchone.return_value = ("LH002", True)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    mock_conn_inst.cursor.return_value = cursor

    mock_list_effective_contracts.return_value = [
        {"operationCode": "GET_RECEIPT", "canonicalVersion": "v1"},
    ]
    mock_list_catalog.return_value = [
        {"operationCode": "GET_RECEIPT", "description": "Get receipt"},
    ]
    mock_list_supported.return_value = [
        {"operationCode": "GET_RECEIPT", "isActive": True},
    ]
    mock_list_endpoints.return_value = [
        {"operationCode": "GET_RECEIPT", "url": "https://example.com"},
    ]
    mock_list_mappings.return_value = []

    mock_my_allowlist.return_value = {
        "statusCode": 200,
        "body": json.dumps({
            "outbound": [{"sourceVendor": "LH002", "targetVendor": "LH003", "operation": "GET_RECEIPT"}],
            "inbound": [],
            "eligibleOperations": [{"operationCode": "GET_RECEIPT", "canCallOutbound": True}],
            "accessOutcomes": [],
        }),
    }
    mock_my_operations.return_value = {
        "statusCode": 200,
        "body": json.dumps({
            "outbound": [],
            "inbound": [],
        }),
    }

    event = _config_bundle_event()
    add_jwt_auth(event, "LH002")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["vendorCode"] == "LH002"
    assert "contracts" in body
    assert len(body["contracts"]) == 1
    assert body["contracts"][0]["operationCode"] == "GET_RECEIPT"
    assert "operationsCatalog" in body
    assert len(body["operationsCatalog"]) == 1
    assert "supportedOperations" in body
    assert len(body["supportedOperations"]) == 1
    assert "endpoints" in body
    assert len(body["endpoints"]) == 1
    assert "mappings" in body
    assert body["mappings"] == []
    assert "myAllowlist" in body
    assert "outbound" in body["myAllowlist"]
    assert len(body["myAllowlist"]["outbound"]) == 1
    assert "myOperations" in body
    assert "outbound" in body["myOperations"]
    assert "inbound" in body["myOperations"]


def test_get_config_bundle_missing_vendor_code_returns_401() -> None:
    """When vendor_code is not set (auth bypass), handler returns 401 AUTH_ERROR."""
    event = _config_bundle_event()
    event["vendor_code"] = ""  # Simulate no vendor resolved

    resp = _handle_get_config_bundle(event)

    assert resp["statusCode"] == 401
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "AUTH_ERROR"
