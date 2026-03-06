"""Tests for canonical pass-through in admin registry readiness."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from registry_lambda import handler  # noqa: E402

TEST_ADMIN_JWT = "test-admin-jwt"


def _readiness_get_event(
    vendor_code: str = "LH001",
    operation_code: str | None = None,
) -> dict:
    params: dict[str, str] = {"vendorCode": vendor_code}
    if operation_code:
        params["operationCode"] = operation_code
    return {
        "path": "/v1/registry/readiness",
        "rawPath": "/v1/registry/readiness",
        "httpMethod": "GET",
        "headers": {"Authorization": f"Bearer {TEST_ADMIN_JWT}"},
        "queryStringParameters": params,
        "pathParameters": {},
        "requestContext": {"http": {"method": "GET"}},
    }


def _readiness_batch_event(vendor_codes: list[str], operation_code: str | None = None) -> dict:
    body: dict = {"vendorCodes": vendor_codes}
    if operation_code:
        body["operationCode"] = operation_code
    return {
        "path": "/v1/registry/readiness/batch",
        "rawPath": "/v1/registry/readiness/batch",
        "httpMethod": "POST",
        "headers": {"Authorization": f"Bearer {TEST_ADMIN_JWT}", "Content-Type": "application/json"},
        "body": json.dumps(body),
        "pathParameters": {},
        "requestContext": {"http": {"method": "POST"}},
    }


def _add_registry_jwt_auth(event: dict) -> None:
    """Add JWT authorizer so registry_lambda require_admin_secret passes."""
    ctx = event.get("requestContext") or {}
    ctx["authorizer"] = {"principalId": "admin", "jwt": {"claims": {"sub": "admin-user", "aud": "api://default", "groups": ["admins", "admin"]}}}
    event["requestContext"] = ctx


@patch("registry_lambda._get_vendor_operations_for_readiness")
@patch("registry_lambda._get_connection")
def test_readiness_outbound_get_canonical_only(
    mock_conn_ctx: MagicMock,
    mock_get_ops: MagicMock,
) -> None:
    """Outbound GET, canonical only: no mappings, no vendor contract → mappingConfigured True, usesCanonical* True."""
    mock_get_ops.return_value = ["GET_WEATHER"]
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = cur

    # _batch_load_readiness_inputs query order: endpoints, operations, contracts, mappings, vendor_contracts
    # Plus vendor exists check (fetchone)
    cur.fetchone.return_value = {"1": 1}
    cur.fetchall.side_effect = [
        [  # 1. endpoints
            {
                "vendor_code": "LH001",
                "operation_code": "GET_WEATHER",
                "url": "https://weather.example.com",
                "verification_status": "VERIFIED",
                "last_verified_at": None,
                "last_verification_error": None,
            },
        ],
        [  # 2. operations
            {"operation_code": "GET_WEATHER", "canonical_version": "v1"},
        ],
        [  # 3. operation_contracts (canonical exists)
            {"operation_code": "GET_WEATHER", "canonical_version": "v1"},
        ],
        [  # 4. vendor_operation_mappings (empty - canonical pass-through)
        ],
        [  # 5. vendor_operation_contracts (empty - no override)
        ],
    ]

    event = _readiness_get_event(vendor_code="LH001", operation_code=None)
    _add_registry_jwt_auth(event)
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "items" in body
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["operationCode"] == "GET_WEATHER"
    assert item["mappingConfigured"] is True
    assert item["effectiveMappingConfigured"] is True
    assert item["usesCanonicalRequestMapping"] is True
    assert item["usesCanonicalResponseMapping"] is True
    assert item["hasVendorRequestMapping"] is False
    assert item["hasVendorResponseMapping"] is False
    assert item["overallOk"] is True


@patch("registry_lambda._get_vendor_operations_for_readiness")
@patch("registry_lambda._get_connection")
def test_readiness_outbound_post_canonical_only(
    mock_conn_ctx: MagicMock,
    mock_get_ops: MagicMock,
) -> None:
    """Outbound POST, canonical only: same expectations as GET."""
    mock_get_ops.return_value = ["SEND_WEATHER"]
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = cur

    cur.fetchone.return_value = {"1": 1}
    cur.fetchall.side_effect = [
        [  # endpoints
            {
                "vendor_code": "LH001",
                "operation_code": "SEND_WEATHER",
                "url": "https://api.example.com/weather",
                "verification_status": "VERIFIED",
                "last_verified_at": None,
                "last_verification_error": None,
            },
        ],
        [{"operation_code": "SEND_WEATHER", "canonical_version": "v1"}],
        [{"operation_code": "SEND_WEATHER", "canonical_version": "v1"}],
        [],  # mappings
        [],  # vendor_contracts
    ]

    event = _readiness_get_event(vendor_code="LH001", operation_code=None)
    _add_registry_jwt_auth(event)
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["operationCode"] == "SEND_WEATHER"
    assert item["mappingConfigured"] is True
    assert item["effectiveMappingConfigured"] is True
    assert item["usesCanonicalRequestMapping"] is True
    assert item["usesCanonicalResponseMapping"] is True
    assert item["overallOk"] is True


@patch("registry_lambda._get_vendor_operations_for_readiness")
@patch("registry_lambda._get_connection")
def test_readiness_vendor_override_without_mapping_not_configured(
    mock_conn_ctx: MagicMock,
    mock_get_ops: MagicMock,
) -> None:
    """Vendor override contract without mapping → mappingConfigured False, usesCanonical* False, overallOk False."""
    mock_get_ops.return_value = ["GET_WEATHER"]
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = cur

    cur.fetchone.return_value = {"1": 1}
    cur.fetchall.side_effect = [
        [  # endpoints
            {
                "vendor_code": "LH001",
                "operation_code": "GET_WEATHER",
                "url": "https://weather.example.com",
                "verification_status": "VERIFIED",
                "last_verified_at": None,
                "last_verification_error": None,
            },
        ],
        [{"operation_code": "GET_WEATHER", "canonical_version": "v1"}],
        [{"operation_code": "GET_WEATHER", "canonical_version": "v1"}],
        [],  # mappings - empty
        [  # vendor_contracts - has override
            {"operation_code": "GET_WEATHER", "canonical_version": "v1"},
        ],
    ]

    event = _readiness_get_event(vendor_code="LH001", operation_code=None)
    _add_registry_jwt_auth(event)
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["operationCode"] == "GET_WEATHER"
    assert item["mappingConfigured"] is False
    assert item.get("effectiveMappingConfigured") is False
    assert item["usesCanonicalRequestMapping"] is False
    assert item["usesCanonicalResponseMapping"] is False
    assert item["overallOk"] is False
