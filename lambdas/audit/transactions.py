"""Read-only access to transactions table with filtering and pagination."""

from __future__ import annotations

from typing import Any

from db import execute_query, execute_scalar, get_connection
from psycopg2 import sql
from validation import DEFAULT_LIMIT, MAX_LIMIT

SCHEMA = "data_plane"
TABLE = "transactions"


def get_by_id(transaction_id: str) -> dict[str, Any] | None:
    """Get a single transaction by transaction_id."""
    with get_connection() as conn:
        q = sql.SQL(
            """
            SELECT id, transaction_id, correlation_id, source_vendor, target_vendor,
                   operation, idempotency_key, status, created_at
            FROM {}.{}
            WHERE transaction_id = %s
            """
        ).format(sql.Identifier(SCHEMA), sql.Identifier(TABLE))
        rows = execute_query(conn, q, (transaction_id,))
        return rows[0] if rows else None


def query_transactions(
    *,
    transaction_id: str | None = None,
    correlation_id: str | None = None,
    source_vendor: str | None = None,
    target_vendor: str | None = None,
    operation: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """
    Query transactions with filtering and pagination.

    Returns (rows, total_count).
    """
    limit = min(max(1, limit), MAX_LIMIT)
    offset = max(0, offset)

    conditions: list[sql.Composable] = []
    params: list[Any] = []

    if transaction_id:
        conditions.append(sql.SQL("transaction_id = %s"))
        params.append(transaction_id)
    if correlation_id:
        conditions.append(sql.SQL("correlation_id = %s"))
        params.append(correlation_id)
    if source_vendor:
        conditions.append(sql.SQL("source_vendor = %s"))
        params.append(source_vendor)
    if target_vendor:
        conditions.append(sql.SQL("target_vendor = %s"))
        params.append(target_vendor)
    if operation:
        conditions.append(sql.SQL("operation = %s"))
        params.append(operation)
    if status:
        conditions.append(sql.SQL("status = %s"))
        params.append(status)
    if date_from:
        conditions.append(sql.SQL("created_at >= %s::timestamptz"))
        params.append(date_from)
    if date_to:
        conditions.append(sql.SQL("created_at <= %s::timestamptz"))
        params.append(date_to)

    where = sql.SQL(" AND ").join(conditions) if conditions else sql.SQL("TRUE")

    with get_connection() as conn:
        # Count total matching rows
        count_query = sql.SQL("SELECT COUNT(*) FROM {}.{} WHERE {}").format(
            sql.Identifier(SCHEMA),
            sql.Identifier(TABLE),
            where,
        )
        total = execute_scalar(conn, count_query, tuple(params))

        # Fetch paginated rows
        data_query = sql.SQL(
            """
            SELECT id, transaction_id, correlation_id, source_vendor, target_vendor,
                   operation, idempotency_key, status, created_at
            FROM {}.{}
            WHERE {}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """
        ).format(
            sql.Identifier(SCHEMA),
            sql.Identifier(TABLE),
            where,
        )
        rows = execute_query(conn, data_query, tuple(params) + (limit, offset))

    return rows, total
