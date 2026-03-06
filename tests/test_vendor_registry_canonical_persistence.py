"""Tests for canonical mapping persistence in vendor Flow Builder and operations mappings."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from vendor_registry_lambda import handler  # noqa: E402
from vendor_registry_jwt import add_jwt_auth  # noqa: E402


def _event(method: str, path: str, body: dict | None = None) -> dict:
    return {
        "path": path,
        "rawPath": path,
        "httpMethod": method,
        "pathParameters": {},
        "queryStringParameters": {},
        "requestContext": {"http": {"method": method}, "requestId": "test-req-id"},
        "headers": {},
        "body": json.dumps(body) if body is not None else None,
    }


@patch("vendor_registry_lambda._get_connection")
def test_put_operation_mappings_canonical_response_persists_empty_mapping(mock_conn_ctx: MagicMock) -> None:
    """PUT mappings with response.mapping=null creates change request (canonical mode; admin applies)."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    def execute_side_effect(query, params=()):
        q = str(query) if hasattr(query, "decode") else str(query)
        cur = mock_conn.cursor.return_value.__enter__.return_value
        cur.fetchall.return_value = []
        cur.rowcount = 1
        if "vendors" in q and "vendor_code" in q:
            cur.fetchone.return_value = ("LH001", True)
        elif "vendor_supported_operations" in q or "vendor_operation_allowlist" in q:
            cur.fetchone.return_value = {1: 1}
        elif "vendor_change_requests" in q:
            cur.fetchone.return_value = {"id": "cr-canon-123"}
        else:
            cur.fetchone.return_value = None

    mock_conn.cursor.return_value.__enter__.return_value.execute.side_effect = execute_side_effect

    payload = {
        "request": {"direction": "CANONICAL_TO_TARGET_REQUEST", "mapping": {"a": "$.x"}},
        "response": {"direction": "TARGET_TO_CANONICAL_RESPONSE", "mapping": None},
    }
    event = _event("PUT", "/v1/vendor/operations/GET_WEATHER/v1/mappings", payload)
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 202
    body = json.loads(resp["body"])
    assert body["status"] == "PENDING"
    assert "changeRequestId" in body


@patch("vendor_registry_lambda._get_connection")
def test_get_operation_mappings_returns_canonical_flags(mock_conn_ctx: MagicMock) -> None:
    """GET mappings returns usesCanonicalRequest/usesCanonicalResponse when rows have empty mapping."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    mapping_iter = iter([
        {"mapping": {}},
        {"mapping": {}},
    ])

    def execute_side_effect(query, params=()):
        q = str(query) if hasattr(query, "decode") else str(query)
        cur = mock_conn.cursor.return_value.__enter__.return_value
        cur.fetchall.return_value = []
        if "vendors" in q and "vendor_code" in q:
            cur.fetchone.return_value = ("LH001", True)
        elif "vendor_supported_operations" in q or "vendor_operation_allowlist" in q:
            cur.fetchone.return_value = {1: 1}
        elif "vendor_operation_mappings" in q and "SELECT mapping" in q:
            try:
                cur.fetchone.return_value = next(mapping_iter)
            except StopIteration:
                cur.fetchone.return_value = None
        else:
            cur.fetchone.return_value = None

    mock_conn.cursor.return_value.__enter__.return_value.execute.side_effect = execute_side_effect

    event = _event("GET", "/v1/vendor/operations/GET_WEATHER/v1/mappings")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body.get("usesCanonicalRequest") is True
    assert body.get("usesCanonicalResponse") is True
    assert body.get("request", {}).get("mapping") is None
    assert body.get("response", {}).get("mapping") is None


@patch("vendor_registry_lambda._get_connection")
def test_get_flow_returns_canonical_flags(mock_conn_ctx: MagicMock) -> None:
    """GET flow returns usesCanonicalRequest/usesCanonicalResponse when canonical rows present."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    mapping_iter = iter([
        {"mapping": {}},
        {"mapping": {}},
    ])

    def execute_side_effect(query, params=()):
        q = str(query) if hasattr(query, "decode") else str(query)
        cur = mock_conn.cursor.return_value.__enter__.return_value
        cur.fetchall.return_value = []
        if "vendors" in q and "vendor_code" in q:
            cur.fetchone.return_value = ("LH001", True)
        elif "vendor_supported_operations" in q or "vendor_operation_allowlist" in q:
            cur.fetchone.return_value = {1: 1}
        elif "operation_contracts" in q and "vendor_operation_contracts" not in q:
            cur.fetchone.return_value = {"request_schema": {"type": "object"}, "response_schema": {"type": "object"}}
        elif "vendor_operation_contracts" in q:
            cur.fetchone.return_value = None
        elif "vendor_operation_mappings" in q and "SELECT" in q:
            try:
                cur.fetchone.return_value = next(mapping_iter)
            except StopIteration:
                cur.fetchone.return_value = None
        elif "vendor_flow_layouts" in q:
            cur.fetchone.return_value = None
        elif "vendor_endpoints" in q:
            cur.fetchone.return_value = None
        else:
            cur.fetchone.return_value = None

    mock_conn.cursor.return_value.__enter__.return_value.execute.side_effect = execute_side_effect

    event = _event("GET", "/v1/vendor/flows/GET_WEATHER/v1")
    add_jwt_auth(event, "LH001")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body.get("usesCanonicalRequest") is True
    assert body.get("usesCanonicalResponse") is True
    assert body.get("requestMapping") is None
    assert body.get("responseMapping") is None
