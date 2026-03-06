"""Unit tests for hasContract / GET /v1/vendor/contracts logic.

hasContract becomes True when the vendor UI sees at least one contract item for an operation.
This tests both explicit vendor_operation_contracts and canonical-backed contracts
(vendor in vendor_supported_operations + canonical in operation_contracts, no explicit vendor row).

Covers: GET_RECEIPT v1 showing 'Contract · Missing' despite Admin having canonical contract.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from vendor_registry_lambda import _list_contracts, handler  # noqa: E402
from vendor_registry_jwt import add_jwt_auth  # noqa: E402


def _contracts_event() -> dict:
    return {
        "path": "/v1/vendor/contracts",
        "rawPath": "/v1/vendor/contracts",
        "httpMethod": "GET",
        "pathParameters": {},
        "queryStringParameters": {},
        "requestContext": {"http": {"method": "GET"}, "requestId": "test-req-id"},
        "headers": {},
    }


def _mock_conn_for_list_contracts(
    vendor_contracts: list[dict],
    vendor_supported: list[dict],
    operation_contracts: list[dict],
) -> MagicMock:
    """Build mock connection that returns given data for _list_contracts queries."""
    mock_cursor = MagicMock()

    def execute_side_effect(query, params=()):
        q = str(query)
        if "vendors" in q and "vendor_code" in q:
            mock_cursor.fetchone.return_value = ("LH001", True)
        elif "vendor_operation_contracts" in q and "vendor_supported" not in q:
            mock_cursor.fetchall.return_value = vendor_contracts
        elif "vendor_supported_operations" in q:
            mock_cursor.fetchall.return_value = vendor_supported
        elif "operation_contracts" in q:
            mock_cursor.fetchall.return_value = operation_contracts
        else:
            mock_cursor.fetchall.return_value = []

    mock_cursor.execute.side_effect = execute_side_effect
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    return mock_conn


def test_list_contracts_explicit_vendor_contract_returns_it() -> None:
    """Explicit vendor_operation_contracts row → item returned → hasContract True."""
    conn = _mock_conn_for_list_contracts(
        vendor_contracts=[
            {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "id": "uuid-1"},
        ],
        vendor_supported=[],
        operation_contracts=[],
    )
    items = _list_contracts(conn, "LH001")
    assert len(items) == 1
    assert items[0]["operationCode"] == "GET_RECEIPT"
    assert items[0]["canonicalVersion"] == "v1"
    # Frontend: hasContract = vendorContracts.some(c => c.operationCode === "GET_RECEIPT")
    assert any(c.get("operationCode") == "GET_RECEIPT" for c in items)


def test_list_contracts_canonical_backed_when_no_vendor_contract() -> None:
    """Canonical-backed: vendor has op in supported, operation_contracts has canonical, no vendor row.
    Covers GET_RECEIPT v1 'Contract · Missing' fix."""
    conn = _mock_conn_for_list_contracts(
        vendor_contracts=[],
        vendor_supported=[
            {"operation_code": "GET_RECEIPT", "canonical_version": "v1"},
        ],
        operation_contracts=[
            {"operation_code": "GET_RECEIPT", "canonical_version": "v1"},
        ],
    )
    items = _list_contracts(conn, "LH001")
    assert len(items) == 1
    assert items[0]["operationCode"] == "GET_RECEIPT"
    assert items[0]["canonicalVersion"] == "v1"
    assert items[0].get("id") is None  # synthetic, no DB id
    assert any(c.get("operationCode") == "GET_RECEIPT" for c in items)


def test_list_contracts_no_canonical_no_contract_returned() -> None:
    """Vendor has op in supported but operation_contracts has no canonical → no contract item."""
    conn = _mock_conn_for_list_contracts(
        vendor_contracts=[],
        vendor_supported=[
            {"operation_code": "GET_RECEIPT", "canonical_version": "v1"},
        ],
        operation_contracts=[],  # No canonical published
    )
    items = _list_contracts(conn, "LH001")
    assert len(items) == 0
    assert not any(c.get("operationCode") == "GET_RECEIPT" for c in items)


def test_list_contracts_explicit_takes_precedence_no_duplicate() -> None:
    """Explicit vendor contract exists → canonical-backed logic must not add duplicate."""
    conn = _mock_conn_for_list_contracts(
        vendor_contracts=[
            {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "id": "uuid-1"},
        ],
        vendor_supported=[
            {"operation_code": "GET_RECEIPT", "canonical_version": "v1"},
        ],
        operation_contracts=[
            {"operation_code": "GET_RECEIPT", "canonical_version": "v1"},
        ],
    )
    items = _list_contracts(conn, "LH001")
    assert len(items) == 1
    assert items[0].get("id") == "uuid-1"


def test_list_contracts_version_must_match_canonical() -> None:
    """Supported op with v2 but operation_contracts only has v1 → no canonical-backed item for v2."""
    conn = _mock_conn_for_list_contracts(
        vendor_contracts=[],
        vendor_supported=[
            {"operation_code": "GET_RECEIPT", "canonical_version": "v2"},
        ],
        operation_contracts=[
            {"operation_code": "GET_RECEIPT", "canonical_version": "v1"},
        ],
    )
    items = _list_contracts(conn, "LH001")
    assert len(items) == 0


def test_get_vendor_contracts_endpoint_canonical_backed() -> None:
    """GET /v1/vendor/contracts returns canonical-backed item → UI hasContract true."""
    with patch("vendor_registry_lambda._get_connection") as mock_conn_ctx:
        conn = _mock_conn_for_list_contracts(
            vendor_contracts=[],
            vendor_supported=[
                {"operation_code": "GET_RECEIPT", "canonical_version": "v1"},
            ],
            operation_contracts=[
                {"operation_code": "GET_RECEIPT", "canonical_version": "v1"},
            ],
        )
        mock_conn_ctx.return_value.__enter__.return_value = conn

        event = _contracts_event()
        add_jwt_auth(event, "LH001")
        resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    items = body.get("items", [])
    assert len(items) == 1
    assert items[0]["operationCode"] == "GET_RECEIPT"
    # Frontend readinessModel: hasContract = vendorContracts.some(c => c.operationCode === op)
    assert any(c.get("operationCode") == "GET_RECEIPT" for c in items)
