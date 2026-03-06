"""Unit tests for Vendor Policy Preview endpoint."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from vendor_registry_jwt import add_jwt_auth  # noqa: E402
from vendor_registry_lambda import handler  # noqa: E402


def _event(body: dict[str, object]) -> dict:
    return {
        "path": "/v1/vendor/policy/preview",
        "rawPath": "/v1/vendor/policy/preview",
        "httpMethod": "POST",
        "pathParameters": {},
        "queryStringParameters": {},
        "requestContext": {"http": {"method": "POST"}, "requestId": "test-req-id"},
        "headers": {},
        "body": json.dumps(body),
    }


def _setup_vendor_auth_cursor(mock_conn_ctx: MagicMock) -> None:
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    cursor.fetchone.return_value = ("LH001", True)
    mock_conn.cursor.return_value = cursor


@patch("vendor_registry_lambda._load_operation_policy_row")
@patch("vendor_registry_lambda.is_feature_enabled_for_vendor")
@patch("vendor_registry_lambda.load_effective_contract_optional")
@patch("vendor_registry_lambda._load_endpoint")
@patch("vendor_registry_lambda._load_allowlist_for_vendor")
@patch("vendor_registry_lambda._get_connection")
def test_policy_preview_allowed_when_allowlist_exists(
    mock_conn_ctx: MagicMock,
    mock_load_allowlist: MagicMock,
    mock_load_endpoint: MagicMock,
    mock_load_contract: MagicMock,
    mock_ai_gate: MagicMock,
    mock_operation_row: MagicMock,
) -> None:
    _setup_vendor_auth_cursor(mock_conn_ctx)
    mock_load_allowlist.return_value = [
        {
            "source_vendor_code": "LH001",
            "target_vendor_code": "LH002",
            "operation_code": "GET_RECEIPT",
            "flow_direction": "BOTH",
        }
    ]
    mock_load_endpoint.return_value = {"verification_status": "VERIFIED"}
    mock_load_contract.return_value = {"source": "canonical"}
    mock_ai_gate.return_value = True
    mock_operation_row.return_value = {
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "ai_presentation_mode": "RAW_AND_FORMATTED",
    }

    event = _event(
        {
            "operationCode": "GET_RECEIPT",
            "targetVendorCode": "LH002",
            "aiRequested": False,
        }
    )
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["allowed"] is True
    assert body["reason"] == "ALLOWED"
    assert body["checks"]["allowlist"]["passed"] is True


@patch("vendor_registry_lambda._load_operation_policy_row")
@patch("vendor_registry_lambda.is_feature_enabled_for_vendor")
@patch("vendor_registry_lambda.load_effective_contract_optional")
@patch("vendor_registry_lambda._load_endpoint")
@patch("vendor_registry_lambda._load_allowlist_for_vendor")
@patch("vendor_registry_lambda._get_connection")
def test_policy_preview_blocked_when_allowlist_missing(
    mock_conn_ctx: MagicMock,
    mock_load_allowlist: MagicMock,
    mock_load_endpoint: MagicMock,
    mock_load_contract: MagicMock,
    mock_ai_gate: MagicMock,
    mock_operation_row: MagicMock,
) -> None:
    _setup_vendor_auth_cursor(mock_conn_ctx)
    mock_load_allowlist.return_value = []
    mock_load_endpoint.return_value = {"verification_status": "VERIFIED"}
    mock_load_contract.return_value = {"source": "canonical"}
    mock_ai_gate.return_value = True
    mock_operation_row.return_value = {
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "ai_presentation_mode": "RAW_AND_FORMATTED",
    }

    event = _event(
        {
            "operationCode": "GET_RECEIPT",
            "targetVendorCode": "LH002",
            "aiRequested": False,
        }
    )
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["allowed"] is False
    assert body["reason"] == "ALLOWLIST_MISSING"
    assert body["checks"]["allowlist"]["passed"] is False
    assert body["whatToFix"]


@patch("vendor_registry_lambda._load_operation_policy_row")
@patch("vendor_registry_lambda.is_feature_enabled_for_vendor")
@patch("vendor_registry_lambda.load_effective_contract_optional")
@patch("vendor_registry_lambda._load_endpoint")
@patch("vendor_registry_lambda._load_allowlist_for_vendor")
@patch("vendor_registry_lambda._get_connection")
def test_policy_preview_ignores_body_vendor_spoof(
    mock_conn_ctx: MagicMock,
    mock_load_allowlist: MagicMock,
    mock_load_endpoint: MagicMock,
    mock_load_contract: MagicMock,
    mock_ai_gate: MagicMock,
    mock_operation_row: MagicMock,
) -> None:
    _setup_vendor_auth_cursor(mock_conn_ctx)
    mock_load_allowlist.return_value = [
        {
            "source_vendor_code": "LH001",
            "target_vendor_code": "LH002",
            "operation_code": "GET_RECEIPT",
            "flow_direction": "BOTH",
        }
    ]
    mock_load_endpoint.return_value = {"verification_status": "VERIFIED"}
    mock_load_contract.return_value = {"source": "canonical"}
    mock_ai_gate.return_value = True
    mock_operation_row.return_value = {
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "ai_presentation_mode": "RAW_AND_FORMATTED",
    }

    event = _event(
        {
            "operationCode": "GET_RECEIPT",
            "targetVendorCode": "LH002",
            "sourceVendorCode": "EVIL999",
            "aiRequested": False,
        }
    )
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["allowed"] is True
    assert body["checks"]["jwt"]["passed"] is True
