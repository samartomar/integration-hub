"""Allowlist repository - database access for vendor_operation_allowlist."""

from __future__ import annotations

from typing import Any

from db import execute_mutation, execute_one, execute_query, get_connection
from psycopg2 import sql

SCHEMA = "control_plane"
TABLE = "vendor_operation_allowlist"


def list_all() -> list[dict[str, Any]]:
    """List all allowlist entries with vendor and operation names."""
    with get_connection() as conn:
        q = sql.SQL(
            """
            SELECT voa.id, voa.vendor_id, voa.operation_id, voa.created_at,
                   v.name AS vendor_name, o.name AS operation_name
            FROM {}.{} voa
            JOIN {}.vendors v ON v.id = voa.vendor_id
            JOIN {}.operations o ON o.id = voa.operation_id
            ORDER BY v.name, o.name
            """
        ).format(
            sql.Identifier(SCHEMA),
            sql.Identifier(TABLE),
            sql.Identifier(SCHEMA),
            sql.Identifier(SCHEMA),
        )
        return execute_query(conn, q)


def get_by_id(allowlist_id: str) -> dict[str, Any] | None:
    """Get an allowlist entry by ID."""
    with get_connection() as conn:
        q = sql.SQL(
            "SELECT id, vendor_id, operation_id, created_at FROM {}.{} WHERE id = %s"
        ).format(sql.Identifier(SCHEMA), sql.Identifier(TABLE))
        return execute_one(conn, q, (allowlist_id,))


def get_by_vendor_operation(vendor_id: str, operation_id: str) -> dict[str, Any] | None:
    """Get an allowlist entry by vendor_id and operation_id."""
    with get_connection() as conn:
        q = sql.SQL(
            "SELECT id, vendor_id, operation_id, created_at FROM {}.{} WHERE vendor_id = %s AND operation_id = %s"
        ).format(sql.Identifier(SCHEMA), sql.Identifier(TABLE))
        return execute_one(conn, q, (vendor_id, operation_id))


def insert(vendor_id: str, operation_id: str) -> dict[str, Any]:
    """Insert an allowlist entry. Returns created row."""
    with get_connection() as conn:
        q = sql.SQL(
            "INSERT INTO {}.{} (vendor_id, operation_id) VALUES (%s, %s) RETURNING id, vendor_id, operation_id, created_at"
        ).format(sql.Identifier(SCHEMA), sql.Identifier(TABLE))
        row = execute_one(conn, q, (vendor_id, operation_id))
        assert row is not None
        return row


def delete(allowlist_id: str) -> bool:
    """Delete an allowlist entry. Returns True if deleted."""
    with get_connection() as conn:
        q = sql.SQL("DELETE FROM {}.{} WHERE id = %s").format(
            sql.Identifier(SCHEMA),
            sql.Identifier(TABLE),
        )
        return execute_mutation(conn, q, (allowlist_id,)) > 0
