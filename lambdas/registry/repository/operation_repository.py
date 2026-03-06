"""Operation repository - database access for operations."""

from __future__ import annotations

from typing import Any

from db import execute_mutation, execute_one, execute_query, get_connection
from psycopg2 import sql

SCHEMA = "control_plane"
TABLE = "operations"


def list_all() -> list[dict[str, Any]]:
    """List all operations."""
    with get_connection() as conn:
        q = sql.SQL(
            "SELECT id, name, description, created_at, updated_at FROM {}.{} ORDER BY name"
        ).format(sql.Identifier(SCHEMA), sql.Identifier(TABLE))
        return execute_query(conn, q)


def get_by_id(operation_id: str) -> dict[str, Any] | None:
    """Get an operation by ID."""
    with get_connection() as conn:
        q = sql.SQL(
            "SELECT id, name, description, created_at, updated_at FROM {}.{} WHERE id = %s"
        ).format(sql.Identifier(SCHEMA), sql.Identifier(TABLE))
        return execute_one(conn, q, (operation_id,))


def insert(name: str, description: str | None = None) -> dict[str, Any]:
    """Insert an operation. Returns created row."""
    with get_connection() as conn:
        q = sql.SQL(
            "INSERT INTO {}.{} (name, description) VALUES (%s, %s) RETURNING id, name, description, created_at, updated_at"
        ).format(sql.Identifier(SCHEMA), sql.Identifier(TABLE))
        row = execute_one(conn, q, (name, description))
        assert row is not None
        return row


def update(
    operation_id: str,
    name: str | None = None,
    description: str | None = None,
) -> dict[str, Any] | None:
    """Update an operation. Returns updated row or None."""
    with get_connection() as conn:
        q = sql.SQL(
            """
            UPDATE {}.{} SET
                name = COALESCE(%s, name),
                description = COALESCE(%s, description),
                updated_at = now()
            WHERE id = %s
            RETURNING id, name, description, created_at, updated_at
            """
        ).format(sql.Identifier(SCHEMA), sql.Identifier(TABLE))
        return execute_one(conn, q, (name, description, operation_id))


def delete(operation_id: str) -> bool:
    """Delete an operation. Returns True if deleted."""
    with get_connection() as conn:
        q = sql.SQL("DELETE FROM {}.{} WHERE id = %s").format(
            sql.Identifier(SCHEMA),
            sql.Identifier(TABLE),
        )
        return execute_mutation(conn, q, (operation_id,)) > 0
