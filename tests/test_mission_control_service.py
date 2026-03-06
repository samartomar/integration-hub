"""Tests for mission_control_service - read-only canonical/runtime transaction visibility."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src"))

from audit.mission_control_service import (
    get_mission_control_transaction,
    list_mission_control_transactions,
)


def _mock_row(
    transaction_id="tx-1",
    correlation_id="corr-1",
    source_vendor="LH001",
    target_vendor="LH002",
    operation="GET_VERIFY_MEMBER_ELIGIBILITY",
    status="completed",
    created_at=None,
    request_body=None,
    canonical_request_body=None,
    target_request_body=None,
    parent_transaction_id=None,
):
    from datetime import datetime, timezone

    return {
        "transaction_id": transaction_id,
        "correlation_id": correlation_id,
        "source_vendor": source_vendor,
        "target_vendor": target_vendor,
        "operation": operation,
        "status": status,
        "created_at": created_at or datetime.now(timezone.utc),
        "request_body": request_body,
        "canonical_request_body": canonical_request_body,
        "target_request_body": target_request_body,
        "parent_transaction_id": parent_transaction_id,
    }


def test_list_returns_recent_items() -> None:
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchall.return_value = [
        _mock_row("tx-1", "corr-1", "LH001", "LH002", "GET_VERIFY_MEMBER_ELIGIBILITY", "completed"),
        _mock_row("tx-2", "corr-2", "LH001", "LH003", "SEND_RECEIPT", "pending"),
    ]

    items = list_mission_control_transactions(conn, filters={}, limit=50)
    assert len(items) == 2
    assert items[0]["transactionId"] == "tx-1"
    assert items[0]["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert items[0]["sourceVendor"] == "LH001"
    assert items[0]["targetVendor"] == "LH002"
    assert items[0]["correlationId"] == "corr-1"
    assert items[0]["status"] == "completed"
    assert items[0]["mode"] == "EXECUTE"
    assert "summary" in items[0]


def test_list_filter_by_operation_code() -> None:
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchall.return_value = [
        _mock_row("tx-1", operation="GET_VERIFY_MEMBER_ELIGIBILITY"),
    ]

    items = list_mission_control_transactions(
        conn, filters={"operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY"}, limit=50
    )
    assert len(items) == 1
    assert items[0]["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    cur.execute.assert_called_once()
    call_args = cur.execute.call_args[0][1]
    assert "GET_VERIFY_MEMBER_ELIGIBILITY" in call_args


def test_list_filter_by_source_vendor() -> None:
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchall.return_value = [_mock_row("tx-1", source_vendor="LH001")]

    items = list_mission_control_transactions(conn, filters={"sourceVendor": "LH001"}, limit=50)
    assert len(items) == 1
    assert items[0]["sourceVendor"] == "LH001"
    call_args = cur.execute.call_args[0][1]
    assert "LH001" in call_args


def test_list_filter_by_status() -> None:
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchall.return_value = [_mock_row("tx-1", status="completed")]

    items = list_mission_control_transactions(conn, filters={"status": "completed"}, limit=50)
    assert len(items) == 1
    assert items[0]["status"] == "completed"


def test_list_filter_by_mode_in_python() -> None:
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchall.return_value = [
        _mock_row("tx-1", request_body={"dryRun": True}),
        _mock_row("tx-2", request_body={}),
    ]

    items = list_mission_control_transactions(conn, filters={"mode": "DRY_RUN"}, limit=50)
    assert len(items) == 1
    assert items[0]["mode"] == "DRY_RUN"
    assert items[0]["transactionId"] == "tx-1"


def test_detail_returns_timeline_and_summary() -> None:
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchone.side_effect = [
        _mock_row(
            "tx-1",
            canonical_request_body={"operationCode": "GET_ELIGIBILITY", "version": "1.0"},
            target_request_body={"targetVendor": "LH002"},
        ),
    ]
    cur.fetchall.side_effect = [
        [
            {
                "created_at": "2026-03-05T12:00:00Z",
                "action": "ROUTE_START",
                "vendor_code": "LH001",
                "details": {"message": "Started"},
            },
        ],
    ]

    detail = get_mission_control_transaction(conn, "tx-1")
    assert detail is not None
    assert detail["transactionId"] == "tx-1"
    assert detail["canonicalVersion"] == "1.0"
    # Metadata-only: no full payload bodies; runtimeRequestPreview has safe metadata only
    assert detail.get("runtimeRequestPreview") is not None
    assert detail["runtimeRequestPreview"].get("targetVendor") == "LH002"
    assert "canonicalRequestEnvelope" not in detail  # payload bodies not exposed
    assert len(detail["timeline"]) == 1
    assert detail["timeline"][0]["eventType"] == "ROUTE_START"
    assert "notes" in detail


def test_detail_not_found_returns_none() -> None:
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchone.return_value = None

    detail = get_mission_control_transaction(conn, "nonexistent")
    assert detail is None


def test_canonical_fields_included_when_available() -> None:
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchall.return_value = [
        _mock_row(
            "tx-1",
            canonical_request_body={"version": "1.0", "dryRun": False},
        ),
    ]

    items = list_mission_control_transactions(conn, filters={}, limit=50)
    assert items[0]["canonicalVersion"] == "1.0"
    assert items[0]["mode"] == "EXECUTE"


def test_sensitive_payload_bodies_not_exposed() -> None:
    """Metadata-only: full request/response bodies must not appear in detail."""
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchone.side_effect = [
        _mock_row(
            "tx-1",
            canonical_request_body={"operationCode": "X", "version": "1.0", "payload": {"ssn": "123-45-6789"}},
            target_request_body={"targetVendor": "LH002", "body": {"sensitive": True}},
        ),
    ]
    cur.fetchall.side_effect = [[]]

    detail = get_mission_control_transaction(conn, "tx-1")
    assert detail is not None
    # Safe metadata only; no payload/body content
    assert "canonicalRequestEnvelope" not in detail
    prev = detail.get("runtimeRequestPreview") or {}
    assert "payload" not in prev
    assert "body" not in prev
    assert "ssn" not in str(prev)
    resp = detail.get("responseSummary") or {}
    assert "targetResponseBody" not in resp
    assert "canonicalResponseBody" not in resp


def test_missing_canonical_fields_produce_notes() -> None:
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchone.side_effect = [_mock_row("tx-1", request_body={}, canonical_request_body=None)]
    cur.fetchall.side_effect = [[]]

    detail = get_mission_control_transaction(conn, "tx-1")
    assert detail is not None
    assert "notes" in detail
    assert any("canonicalVersion" in n for n in detail["notes"])
    assert detail["canonicalVersion"] is None
