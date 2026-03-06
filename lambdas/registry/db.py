"""Database connection pool and utilities."""

from __future__ import annotations

import json
import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from psycopg2 import pool, sql
from psycopg2.extras import RealDictCursor

_pool: pool.ThreadedConnectionPool | None = None


def _get_creds() -> dict[str, str]:
    """Get database credentials from Secrets Manager or environment."""
    secret_arn: str | None = os.environ.get("DB_SECRET_ARN")
    if secret_arn:
        import boto3

        client = boto3.client("secretsmanager")
        response = client.get_secret_value(SecretId=secret_arn)
        raw = json.loads(response["SecretString"])
        return {
            "host": raw["host"],
            "port": str(raw.get("port", 5432)),
            "dbname": raw.get("dbname") or raw.get("database", "integrationhub"),
            "user": raw.get("user") or raw["username"],
            "password": raw["password"],
        }
    return {
        "host": os.environ["DB_HOST"],
        "port": os.environ.get("DB_PORT", "5432"),
        "dbname": os.environ.get("DB_NAME", "integrationhub"),
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
    }


def _get_pool() -> pool.ThreadedConnectionPool:
    """Lazy-initialize connection pool (reused across Lambda invocations)."""
    global _pool
    if _pool is None:
        creds = _get_creds()
        _pool = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=5,
            host=creds["host"],
            port=creds["port"],
            dbname=creds["dbname"],
            user=creds["user"],
            password=creds["password"],
            connect_timeout=10,
        )
    return _pool


@contextmanager
def get_connection() -> Generator[Any, None, None]:
    """Get a connection from the pool."""
    conn = _get_pool().getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _get_pool().putconn(conn)


def execute_query(
    conn: Any,
    query: sql.Composed,
    params: tuple[Any, ...] | None = None,
) -> list[dict[str, Any]]:
    """Execute a parameterized query and return rows as dicts."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params or ())
        return [dict(row) for row in cur.fetchall()]


def execute_one(
    conn: Any,
    query: sql.Composed,
    params: tuple[Any, ...] | None = None,
) -> dict[str, Any] | None:
    """Execute a parameterized query and return the first row or None."""
    rows = execute_query(conn, query, params or ())
    return rows[0] if rows else None


def execute_mutation(
    conn: Any,
    query: sql.Composed,
    params: tuple[Any, ...] | None = None,
) -> int:
    """Execute an INSERT/UPDATE/DELETE and return rowcount."""
    with conn.cursor() as cur:
        cur.execute(query, params or ())
        return cur.rowcount


def ensure_tables(conn: Any) -> None:
    """No-op: schema is managed by Alembic migrations. Tables must exist from alembic upgrade head."""
