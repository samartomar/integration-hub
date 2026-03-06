"""Tests for mapping_utils - effective mapping resolution."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

import pytest


def _mock_conn_with_recorded_sql(
    fetchone_returns: list | None = None,
) -> tuple[MagicMock, list[tuple[str, tuple]]]:
    """Create mock connection that records (sql, params) for each execute call."""
    recorded: list[tuple[str, tuple]] = []
    mock_cursor = MagicMock()
    if fetchone_returns is not None:
        mock_cursor.fetchone.side_effect = fetchone_returns
    else:
        mock_cursor.fetchone.return_value = None

    def execute_side_effect(sql: str | object, params: tuple = ()):
        sql_str = str(sql) if hasattr(sql, "__str__") else sql
        recorded.append((sql_str, params))
        return None

    mock_cursor.execute.side_effect = execute_side_effect
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return mock_conn, recorded


def test_resolve_effective_mapping_no_rows_returns_pass_through() -> None:
    """When no vendor_operation_mappings rows, returns canonical_pass_through."""
    from mapping_utils import resolve_effective_mapping

    mock_conn, recorded = _mock_conn_with_recorded_sql(fetchone_returns=[None, None])

    info = resolve_effective_mapping(
        mock_conn,
        vendor_code="LH001",
        operation_code="GET_RECEIPT",
        canonical_version="v1",
        flow_direction="OUTBOUND",
        role="target",
    )

    assert info.request_source == "canonical_pass_through"
    assert info.response_source == "canonical_pass_through"
    assert info.has_vendor_request_mapping is False
    assert info.has_vendor_response_mapping is False
    assert info.request_mapping is None
    assert info.response_mapping is None
    assert len(recorded) >= 2


def test_resolve_effective_mapping_with_request_mapping() -> None:
    """When FROM_CANONICAL mapping exists, request_source is vendor_mapping."""
    from mapping_utils import resolve_effective_mapping

    req_row = {"mapping": {"txnId": "$.transactionId"}}
    mock_conn, recorded = _mock_conn_with_recorded_sql(fetchone_returns=[req_row, None])

    info = resolve_effective_mapping(
        mock_conn,
        vendor_code="LH001",
        operation_code="GET_RECEIPT",
        canonical_version="v1",
        flow_direction="OUTBOUND",
        role="target",
    )

    assert info.request_source == "vendor_mapping"
    assert info.response_source == "canonical_pass_through"
    assert info.has_vendor_request_mapping is True
    assert info.has_vendor_response_mapping is False
    assert info.request_mapping == {"txnId": "$.transactionId"}
    assert info.response_mapping is None
