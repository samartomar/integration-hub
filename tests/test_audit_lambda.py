"""Unit tests for Audit Lambda - transaction detail with authSummary and contractMappingSummary."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from audit_lambda import (  # noqa: E402
    handler,
    _derive_auth_summary,
    _derive_contract_mapping_summary,
)

JWT_AUTHORIZER = {"principalId": "okta|test", "jwt": {"claims": {"sub": "okta|test"}}}


def _transaction_detail_event(
    transaction_id: str = "tx-123",
    vendor_code: str = "LH001",
) -> dict:
    """Build GET /v1/audit/transactions/{id} event."""
    return {
        "path": f"/v1/audit/transactions/{transaction_id}",
        "rawPath": f"/v1/audit/transactions/{transaction_id}",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {"vendorCode": vendor_code},
        "pathParameters": {"transactionId": transaction_id},
        "requestContext": {"http": {"method": "GET"}, "authorizer": JWT_AUTHORIZER},
    }


@patch("audit_lambda._get_connection")
def test_transaction_detail_returns_404_when_not_found(mock_conn) -> None:
    """GET transaction detail returns 404 when transaction not found."""
    with patch("audit_lambda._get_by_id", return_value=None):
        event = _transaction_detail_event()
        resp = handler(event, None)

    assert resp["statusCode"] == 404
    body = json.loads(resp["body"])
    assert body["error"]["code"] == "NOT_FOUND"


@patch("audit_lambda._get_connection")
def test_transaction_detail_includes_auth_and_contract_summaries(mock_conn) -> None:
    """GET transaction detail returns authSummary and contractMappingSummary."""
    txn_row = {
        "transaction_id": "tx-456",
        "source_vendor": "LH001",
        "target_vendor": "LH002",
        "operation": "GET_RECEIPT",
        "status": "completed",
        "correlation_id": "corr-1",
        "id": 1,
        "idempotency_key": "key-1",
        "created_at": "2024-01-01T00:00:00",
        "request_body": None,
        "response_body": None,
        "canonical_request_body": {"transactionId": "t1"},
        "target_request_body": {"receiptId": "r1"},
        "target_response_body": {"status": "ok"},
        "canonical_response_body": {"status": "ok"},
        "error_code": None,
        "http_status": None,
        "retryable": None,
        "failure_stage": None,
    }

    audit_items = [
        {
            "id": "e1",
            "transactionId": "tx-456",
            "action": "AUTH_API_KEY_SUCCEEDED",
            "vendorCode": "LH001",
            "details": {"vendor_code": "LH001"},
            "createdAt": "2024-01-01T00:00:00",
        },
    ]

    auth_summary = {
        "mode": "API_KEY",
        "sourceVendor": "LH001",
        "idpIssuer": None,
        "idpAudience": None,
        "jwtVendorClaim": None,
        "authProfile": {
            "id": "ap-uuid-1",
            "name": "WeatherAPI profile",
            "authType": "API_KEY_HEADER",
        },
    }

    contract_summary = {
        "operationCode": "GET_RECEIPT",
        "canonicalVersion": "v1",
        "canonical": {"hasRequestSchema": True, "hasResponseSchema": True},
        "sourceVendor": {
            "vendorCode": "LH001",
            "hasVendorContract": True,
            "hasRequestSchema": True,
            "hasResponseSchema": True,
            "hasFromCanonicalRequestMapping": False,
            "hasToCanonicalResponseMapping": False,
        },
        "targetVendor": {
            "vendorCode": "LH002",
            "hasVendorContract": True,
            "hasRequestSchema": True,
            "hasResponseSchema": True,
            "hasFromCanonicalRequestMapping": True,
            "hasToCanonicalResponseMapping": True,
        },
    }

    def fake_get_by_id(conn, tx_id, vendor_code):
        return txn_row

    def fake_query_audit(conn, tx_id, limit=500):
        return audit_items

    def fake_derive_auth(txn, events, conn):
        return auth_summary

    def fake_derive_contract(txn, conn):
        return contract_summary

    with (
        patch("audit_lambda._get_by_id", side_effect=fake_get_by_id),
        patch("audit_lambda._query_audit_events", side_effect=fake_query_audit),
        patch("audit_lambda._derive_auth_summary", side_effect=fake_derive_auth),
        patch("audit_lambda._derive_contract_mapping_summary", side_effect=fake_derive_contract),
    ):
        event = _transaction_detail_event("tx-456", "LH001")
        resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "transaction" in body
    assert body["transaction"]["transaction_id"] == "tx-456"
    assert body["transaction"]["source_vendor"] == "LH001"
    assert "auditEvents" in body
    assert len(body["auditEvents"]) == 1
    assert body["auditEvents"][0]["action"] == "AUTH_API_KEY_SUCCEEDED"
    assert "authSummary" in body
    assert body["authSummary"]["mode"] == "API_KEY"
    assert body["authSummary"]["sourceVendor"] == "LH001"
    assert body["authSummary"]["authProfile"]["authType"] == "API_KEY_HEADER"
    assert "contractMappingSummary" in body
    assert body["contractMappingSummary"]["operationCode"] == "GET_RECEIPT"
    assert body["contractMappingSummary"]["canonical"]["hasRequestSchema"] is True
    assert body["contractMappingSummary"]["targetVendor"]["hasFromCanonicalRequestMapping"] is True


def test_derive_auth_summary_unknown_when_no_events() -> None:
    """authSummary mode is UNKNOWN when no auth events."""
    txn = {"source_vendor": "LH001", "target_vendor": "LH002", "operation": "GET_RECEIPT"}
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchone.return_value = None
    summary = _derive_auth_summary(txn, [], conn)
    assert summary["mode"] == "UNKNOWN"
    assert summary["sourceVendor"] == "LH001"


def test_derive_contract_mapping_summary_empty_when_no_operation() -> None:
    """contractMappingSummary has false/defaults when operation not in DB."""
    txn = {"source_vendor": "LH001", "target_vendor": "LH002", "operation": "UNKNOWN_OP"}
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = None
    conn.cursor.return_value.__enter__.return_value = cur
    summary = _derive_contract_mapping_summary(txn, conn)
    assert summary["operationCode"] == "UNKNOWN_OP"
    assert summary["canonicalVersion"] is None
    assert summary["canonical"]["hasRequestSchema"] is False
    assert summary["sourceVendor"]["hasVendorContract"] is False
    assert summary["targetVendor"]["hasFromCanonicalRequestMapping"] is False


@patch("audit_lambda._get_connection")
@patch("audit_lambda._query_transactions")
def test_get_transactions_list_empty_db_returns_200(mock_query, mock_conn) -> None:
    """GET /v1/audit/transactions with from/to and no transactions returns 200 with empty list."""
    mock_query.return_value = ([], None)
    event = {
        "path": "/v1/audit/transactions",
        "rawPath": "/v1/audit/transactions",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {"from": "2024-01-01T00:00:00", "to": "2024-01-31T23:59:59"},
        "requestContext": {"http": {"method": "GET"}, "authorizer": JWT_AUTHORIZER},
    }
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["transactions"] == []
    assert body["count"] == 0
