#!/usr/bin/env python3
"""
Roll up transactions into data_plane.transaction_metrics_daily.

Run periodically (e.g. Lambda every 15 min, or cron). Requires DATABASE_URL or DB_SECRET_ARN.
Typical: roll up last 2 hours to catch recent data. State can be stored in a simple table
or env (last_processed_ts); for simplicity this script rolls [now - 2h, now).
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.parse
from datetime import UTC, datetime, timedelta


def _get_url() -> str:
    """Build DATABASE_URL from env or Secrets Manager."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    arn = os.environ.get("DB_SECRET_ARN")
    if not arn:
        raise ValueError("DATABASE_URL or DB_SECRET_ARN required")
    r = subprocess.run(
        ["aws", "secretsmanager", "get-secret-value", "--secret-id", arn, "--query", "SecretString", "--output", "text"],
        capture_output=True, text=True, check=False,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr or r.stdout)
    secret = json.loads(r.stdout)
    pw = urllib.parse.quote(str(secret["password"]), safe="")
    user = secret.get("username") or secret.get("user", "clusteradmin")
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    db = secret.get("dbname") or secret.get("database", "integrationhub")
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}"


def main() -> None:
    now = datetime.now(UTC)
    # Roll last 2 hours (overlap to catch late arrivals)
    from_ts = now - timedelta(hours=2)
    to_ts = now
    from_str = from_ts.isoformat().replace("+00:00", "Z")
    to_str = to_ts.isoformat().replace("+00:00", "Z")

    import psycopg2
    conn = psycopg2.connect(_get_url())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT data_plane.rollup_transaction_metrics(%s::timestamptz, %s::timestamptz)",
                (from_str, to_str),
            )
        conn.commit()
        print(f"Rolled up {from_str} to {to_str}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
