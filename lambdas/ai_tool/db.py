"""Database connection and query utilities."""

from __future__ import annotations

import json
import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor


def _get_secret() -> dict[str, str]:
    """Get database credentials from Secrets Manager or environment."""
    import boto3

    secret_arn: str | None = os.environ.get("DB_SECRET_ARN")
    if secret_arn:
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


@contextmanager
def get_connection() -> Generator[Any, None, None]:
    """Context manager for database connections."""
    creds = _get_secret()
    conn = psycopg2.connect(
        host=creds["host"],
        port=creds["port"],
        dbname=creds["dbname"],
        user=creds["user"],
        password=creds["password"],
        connect_timeout=10,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_one(
    conn: Any,
    query: sql.Composed,
    params: tuple[Any, ...] | None = None,
) -> dict[str, Any] | None:
    """Execute a parameterized query and return the first row or None."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        return dict(row) if row else None
