"""Unit tests for effective endpoint resolver (endpoint_utils)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

import pytest

from endpoint_utils import EndpointNotFound, ResolvedEndpoint, load_effective_endpoint


def _make_conn_mock(fetchone_results: list) -> MagicMock:
    """Mock connection with cursor that returns given fetchone results in sequence."""
    cursor = MagicMock()
    cursor.fetchone = MagicMock(side_effect=fetchone_results)
    cursor.execute = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)

    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


def _endpoint_row(
    url: str = "https://example.com/op",
    flow_direction: str = "INBOUND",
    **kwargs: object,
) -> dict:
    """Build endpoint row as returned by vendor_endpoints SELECT."""
    return {
        "id": "ep-uuid-123",
        "vendor_code": "LH001",
        "operation_code": "GET_RECEIPT",
        "flow_direction": flow_direction,
        "url": url,
        "http_method": "POST",
        "payload_format": "JSON",
        "timeout_ms": 8000,
        "vendor_auth_profile_id": None,
        "verification_status": "VERIFIED",
        **kwargs,
    }


def test_load_effective_endpoint_exact_direction_succeeds() -> None:
    """Endpoint exists with expected direction -> exact match succeeds."""
    row = _endpoint_row(url="https://exact.com/op", flow_direction="INBOUND")
    conn = _make_conn_mock([row])

    result = load_effective_endpoint(
        conn, "LH001", "GET_RECEIPT", expected_direction="INBOUND"
    )

    assert isinstance(result, ResolvedEndpoint)
    assert result.url == "https://exact.com/op"
    assert result.method == "POST"
    assert result.source == "exact_match"
    assert result.matched_direction == "INBOUND"
    assert result.row_id == "ep-uuid-123"


def test_load_effective_endpoint_opposite_direction_raises_not_found() -> None:
    """With explicit expected_direction, opposite-direction fallback is not allowed."""
    # Exact INBOUND misses; resolver now raises without cross-direction fallback.
    conn = _make_conn_mock([None])

    with pytest.raises(
        EndpointNotFound,
        match="No active endpoint for LH001 \\+ GET_RECEIPT with flow_direction=INBOUND",
    ):
        load_effective_endpoint(
            conn, "LH001", "GET_RECEIPT", expected_direction="INBOUND"
        )


def test_load_effective_endpoint_no_direction_fallback_succeeds() -> None:
    """No expected_direction -> fallback query only, succeeds if row exists."""
    row = _endpoint_row(url="https://any.com/op")
    conn = _make_conn_mock([row])

    result = load_effective_endpoint(conn, "LH001", "GET_RECEIPT")

    assert result.url == "https://any.com/op"
    assert result.source == "fallback_any"


def test_load_effective_endpoint_none_raises_endpoint_not_found() -> None:
    """No endpoint exists -> EndpointNotFound."""
    conn = _make_conn_mock([None, None])  # exact + fallback both empty

    with pytest.raises(EndpointNotFound, match="No active endpoint for LH001 \\+ GET_RECEIPT"):
        load_effective_endpoint(
            conn, "LH001", "GET_RECEIPT", expected_direction="INBOUND"
        )


def test_load_effective_endpoint_empty_vendor_raises() -> None:
    """Empty vendor_code raises EndpointNotFound."""
    conn = _make_conn_mock([])

    with pytest.raises(EndpointNotFound, match="vendor_code and operation_code required"):
        load_effective_endpoint(conn, "", "GET_RECEIPT")


def test_load_effective_endpoint_invalid_direction_treated_as_none() -> None:
    """Invalid expected_direction (e.g. BOTH) -> treated as None, fallback only."""
    row = _endpoint_row()
    conn = _make_conn_mock([row])

    result = load_effective_endpoint(
        conn, "LH001", "GET_RECEIPT", expected_direction="BOTH"
    )

    assert result.source == "fallback_any"
    # Only one query when exp is None
    assert conn.cursor.return_value.execute.call_count == 1
