"""Vendor repository - database access for vendors."""

from __future__ import annotations

from typing import Any

from db import execute_mutation, execute_one, execute_query, get_connection
from psycopg2 import sql

SCHEMA = "control_plane"
TABLE = "vendors"


def list_all() -> list[dict[str, Any]]:
    """List all vendors."""
    with get_connection() as conn:
        q = sql.SQL("SELECT id, name, description, created_at, updated_at FROM {}.{} ORDER BY name").format(
            sql.Identifier(SCHEMA),
            sql.Identifier(TABLE),
        )
        return execute_query(conn, q)


def get_by_id(vendor_id: str) -> dict[str, Any] | None:
    """Get a vendor by ID."""
    with get_connection() as conn:
        q = sql.SQL(
            "SELECT id, name, description, created_at, updated_at FROM {}.{} WHERE id = %s"
        ).format(sql.Identifier(SCHEMA), sql.Identifier(TABLE))
        return execute_one(conn, q, (vendor_id,))


def insert(name: str, description: str | None = None) -> dict[str, Any]:
    """Insert a vendor. Returns created row."""
    with get_connection() as conn:
        q = sql.SQL(
            "INSERT INTO {}.{} (name, description) VALUES (%s, %s) RETURNING id, name, description, created_at, updated_at"
        ).format(sql.Identifier(SCHEMA), sql.Identifier(TABLE))
        row = execute_one(conn, q, (name, description))
        assert row is not None
        return row


def update(
    vendor_id: str,
    name: str | None = None,
    description: str | None = None,
) -> dict[str, Any] | None:
    """Update a vendor. Returns updated row or None."""
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
        return execute_one(conn, q, (name, description, vendor_id))


def delete(vendor_id: str) -> bool:
    """Delete a vendor. Returns True if deleted."""
    with get_connection() as conn:
        q = sql.SQL("DELETE FROM {}.{} WHERE id = %s").format(
            sql.Identifier(SCHEMA),
            sql.Identifier(TABLE),
        )
        return execute_mutation(conn, q, (vendor_id,)) > 0
