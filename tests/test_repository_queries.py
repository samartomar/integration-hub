"""Unit tests for repository queries: is_active filter, ORDER BY updated_at DESC, LIMIT 1."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

# Mock jwt if not installed (routing_lambda -> jwt_auth -> jwt)
try:
    import jwt as _  # noqa: F401
except ImportError:
    sys.modules["jwt"] = MagicMock()

import pytest


def _mock_conn_with_recorded_sql(
    fetchone_returns: list | None = None,
) -> tuple[MagicMock, list[tuple[str, tuple]]]:
    """Create mock connection that records (sql, params) for each execute call.
    fetchone_returns: if set, side_effect for fetchone (one value per execute); else return_value=None.
    """
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


def _assert_query_clauses(sql: str) -> None:
    """Assert SQL contains is_active filter, ORDER BY updated_at DESC, LIMIT 1."""
    sql_upper = sql.upper()
    assert "IS_ACTIVE" in sql_upper and "TRUE" in sql_upper, f"Expected is_active = true in: {sql[:300]}"
    assert "ORDER BY" in sql_upper, f"Expected ORDER BY in: {sql[:300]}"
    assert "DESC" in sql_upper, f"Expected DESC in: {sql[:300]}"
    assert "LIMIT 1" in sql_upper, f"Expected LIMIT 1 in: {sql[:300]}"


# --- routing_lambda ---


def test_load_operation_contract_canonical_filters_active_orders_desc_limits_one() -> None:
    """load_operation_contract (canonical) uses is_active, ORDER BY updated_at DESC, LIMIT 1."""
    from routing_lambda import load_operation_contract

    mock_conn, recorded = _mock_conn_with_recorded_sql()
    result = load_operation_contract(mock_conn, "GET_RECEIPT", "v1", vendor_code=None)

    assert result is None
    assert len(recorded) >= 1
    sql = recorded[0][0]
    _assert_query_clauses(sql)
    assert "operation_contracts" in sql
    assert "vendor_operation_contracts" not in sql


def test_load_operation_contract_vendor_filters_active_orders_desc_limits_one() -> None:
    """load_operation_contract (vendor) uses is_active, ORDER BY updated_at DESC, LIMIT 1."""
    from routing_lambda import load_operation_contract

    mock_conn, recorded = _mock_conn_with_recorded_sql()
    result = load_operation_contract(
        mock_conn, "GET_RECEIPT", "v1", vendor_code="LH001"
    )

    assert result is None
    assert len(recorded) >= 1
    sql = recorded[0][0]
    _assert_query_clauses(sql)
    assert "vendor_operation_contracts" in sql


def test_load_operation_contract_vendor_falls_back_to_canonical_when_vendor_missing() -> None:
    """When vendor_code provided and vendor_operation_contracts has no row, fall back to operation_contracts."""
    from routing_lambda import load_operation_contract

    canon_row = {
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "request_schema": {"type": "object", "properties": {"transactionId": {"type": "string"}}},
        "response_schema": {"type": "object"},
    }
    mock_conn, recorded = _mock_conn_with_recorded_sql(
        fetchone_returns=[None, canon_row]
    )

    result = load_operation_contract(
        mock_conn, "GET_RECEIPT", "v1", vendor_code="LH001"
    )

    assert result is not None
    assert result["operation_code"] == "GET_RECEIPT"
    assert result["canonical_version"] == "v1"
    assert "request_schema" in result
    assert len(recorded) >= 2
    assert "vendor_operation_contracts" in recorded[0][0]
    assert "operation_contracts" in recorded[1][0]


def test_load_operation_contract_returns_newest_active_row_when_found() -> None:
    """When DB returns one row (newest active), load_operation_contract returns it."""
    from routing_lambda import load_operation_contract

    row = {
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "request_schema": {"type": "object"},
        "response_schema": {"type": "object"},
    }
    mock_conn, recorded = _mock_conn_with_recorded_sql(fetchone_returns=[row])

    result = load_operation_contract(mock_conn, "GET_RECEIPT", "v1")

    assert result is not None
    assert result["operation_code"] == "GET_RECEIPT"
    assert result["canonical_version"] == "v1"
    assert "request_schema" in result


def test_load_vendor_mapping_filters_active_orders_desc_limits_one() -> None:
    """load_vendor_mapping uses is_active, ORDER BY updated_at DESC, LIMIT 1."""
    from routing_lambda import load_vendor_mapping

    mock_conn, recorded = _mock_conn_with_recorded_sql()
    result = load_vendor_mapping(
        mock_conn, "LH001", "GET_RECEIPT", "v1", "TO_CANONICAL"
    )

    assert result is None
    assert len(recorded) >= 1
    sql = recorded[0][0]
    _assert_query_clauses(sql)
    assert "vendor_operation_mappings" in sql


def test_load_vendor_mapping_returns_newest_active_row_when_found() -> None:
    """When DB returns one row, load_vendor_mapping returns mapping dict."""
    from routing_lambda import load_vendor_mapping

    mock_conn, recorded = _mock_conn_with_recorded_sql(
        fetchone_returns=[{"mapping": {"result": "$.result"}}]
    )

    result = load_vendor_mapping(
        mock_conn, "LH001", "GET_RECEIPT", "v1", "TO_CANONICAL"
    )

    assert result == {"result": "$.result"}


def test_validate_control_plane_vendor_endpoints_filters_active_orders_desc_limits_one() -> None:
    """validate_control_plane uses load_effective_endpoint; endpoint queries use is_active, ORDER BY, LIMIT 1."""
    from routing_lambda import validate_control_plane

    def make_row() -> MagicMock:
        r = MagicMock()
        r.get.side_effect = lambda k, d=None: {"canonical_version": "v1"}.get(k, d)
        return r

    mock_conn, recorded = _mock_conn_with_recorded_sql(
        fetchone_returns=[
            make_row(),   # source vendor
            make_row(),   # target vendor
            make_row(),   # operation
            make_row(),   # vendor_supported_operations
            make_row(),   # allowlist
            None,        # load_effective_endpoint exact (INBOUND) - no match
            None,        # load_effective_endpoint fallback - no match
        ]
    )

    with pytest.raises(ValueError, match="No active endpoint"):
        validate_control_plane(mock_conn, "LH001", "LH002", "GET_RECEIPT")

    endpoint_queries = [r[0] for r in recorded if "vendor_endpoints" in r[0] and "url" in r[0]]
    assert len(endpoint_queries) >= 1, "Expected vendor_endpoints SELECT from load_effective_endpoint"
    _assert_query_clauses(endpoint_queries[0])


def test_validate_control_plane_allowlist_query_includes_expected_columns() -> None:
    """validate_control_plane still queries allowlist table and source wildcard support."""
    # Read routing_lambda source to verify wildcard SQL (avoids jwt import in test env)
    routing_path = Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda" / "routing_lambda.py"
    source = routing_path.read_text()
    assert "is_any_source" in source, "Allowlist should use is_any_source for wildcard source"
    assert "is_any_target" not in source, "Target wildcard semantics are no longer used in runtime query"
    assert "vendor_operation_allowlist" in source, "Allowlist table must be queried"


# --- endpoint_verifier_lambda ---


def test_endpoint_verifier_load_operation_contract_filters_active_orders_desc_limits_one() -> None:
    """_load_operation_contract uses is_active, ORDER BY updated_at DESC, LIMIT 1."""
    from endpoint_verifier_lambda import _load_operation_contract

    mock_conn, recorded = _mock_conn_with_recorded_sql()
    result = _load_operation_contract(mock_conn, "GET_RECEIPT", "v1")

    assert result is None
    assert len(recorded) >= 1
    sql = recorded[0][0]
    _assert_query_clauses(sql)
    assert "operation_contracts" in sql


def test_endpoint_verifier_load_operation_contract_returns_newest_active() -> None:
    """When row found, _load_operation_contract returns it."""
    from endpoint_verifier_lambda import _load_operation_contract

    row = {
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "request_schema": {"type": "object"},
    }
    mock_conn, recorded = _mock_conn_with_recorded_sql(fetchone_returns=[row])

    result = _load_operation_contract(mock_conn, "GET_RECEIPT", "v1")

    assert result is not None
    assert result["operation_code"] == "GET_RECEIPT"
    assert result.get("request_schema") == {"type": "object"}


# --- vendor_registry_lambda ---


def test_vendor_registry_load_endpoint_filters_active_orders_desc_limits_one() -> None:
    """_load_endpoint uses is_active, ORDER BY updated_at DESC, LIMIT 1."""
    from vendor_registry_lambda import _load_endpoint

    mock_conn, recorded = _mock_conn_with_recorded_sql()
    result = _load_endpoint(mock_conn, "LH001", "GET_RECEIPT")

    assert result is None
    assert len(recorded) >= 1
    sql = recorded[0][0]
    _assert_query_clauses(sql)
    assert "vendor_endpoints" in sql


def test_vendor_registry_load_endpoint_returns_newest_active() -> None:
    """When row found, _load_endpoint returns it."""
    from vendor_registry_lambda import _load_endpoint

    row = {
        "id": "ep-1",
        "vendor_code": "LH001",
        "operation_code": "GET_RECEIPT",
        "url": "https://api.example.com/receipt",
        "http_method": "GET",
    }
    mock_conn, recorded = _mock_conn_with_recorded_sql(fetchone_returns=[row])

    result = _load_endpoint(mock_conn, "LH001", "GET_RECEIPT")

    assert result is not None
    assert result["vendor_code"] == "LH001"
    assert result["operation_code"] == "GET_RECEIPT"
    assert result["url"] == "https://api.example.com/receipt"


# --- registry_lambda ---


def test_registry_get_contract_filters_active_orders_desc_limits_one() -> None:
    """_get_contract uses is_active, ORDER BY updated_at DESC, LIMIT 1."""
    from registry_lambda import _get_contract

    mock_conn, recorded = _mock_conn_with_recorded_sql()
    result = _get_contract(mock_conn, "GET_RECEIPT", "v1")

    assert result is None
    assert len(recorded) >= 1
    sql = recorded[0][0]
    _assert_query_clauses(sql)
    assert "operation_contracts" in sql


def test_registry_get_contract_returns_newest_active() -> None:
    """When row found, _get_contract returns it."""
    from registry_lambda import _get_contract

    row = {
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "request_schema": {"type": "object"},
        "is_active": True,
    }
    mock_conn, recorded = _mock_conn_with_recorded_sql(fetchone_returns=[row])

    result = _get_contract(mock_conn, "GET_RECEIPT", "v1")

    assert result is not None
    assert result["operation_code"] == "GET_RECEIPT"
    assert result["canonical_version"] == "v1"


# --- ai_tool validation.fetch_request_schema ---


def test_ai_tool_fetch_request_schema_filters_active_orders_desc_limits_one() -> None:
    """fetch_request_schema (operation_contracts) uses is_active, ORDER BY, LIMIT 1."""
    import sys as _sys
    ai_path = str(Path(__file__).resolve().parent.parent / "lambdas" / "ai_tool")
    if ai_path not in _sys.path:
        _sys.path.insert(0, ai_path)

    from validation import fetch_request_schema

    recorded: list[tuple[str, tuple]] = []

    def record_execute_one(conn: object, query: object, params: tuple = ()) -> None:
        recorded.append((str(query), params))
        return None

    with patch("validation.execute_one", side_effect=record_execute_one):
        with patch("validation.get_connection") as mock_gc:
            mock_gc.return_value.__enter__.return_value = MagicMock()
            mock_gc.return_value.__exit__.return_value = False
            result = fetch_request_schema("GET_RECEIPT", "v1")

    assert result is None
    assert len(recorded) >= 1
    sql = recorded[0][0]
    _assert_query_clauses(sql)
    assert "operation_contracts" in sql


def test_ai_tool_fetch_request_schema_returns_newest_active() -> None:
    """When row found, fetch_request_schema returns request_schema."""
    import sys as _sys
    ai_path = str(Path(__file__).resolve().parent.parent / "lambdas" / "ai_tool")
    if ai_path not in _sys.path:
        _sys.path.insert(0, ai_path)

    from validation import fetch_request_schema

    schema = {"type": "object", "required": ["transactionId"]}

    def return_row(conn: object, query: object, params: tuple = ()) -> dict | None:
        return {"request_schema": schema}

    with patch("validation.execute_one", side_effect=return_row):
        with patch("validation.get_connection") as mock_gc:
            mock_gc.return_value.__enter__.return_value = MagicMock()
            mock_gc.return_value.__exit__.return_value = False
            result = fetch_request_schema("GET_RECEIPT", "v1")

    assert result == schema
