#!/usr/bin/env python3
"""
Purge old idempotency_claims rows beyond the intended window (24–72 hours).

Design: idempotency_claims is for replay detection; we only need recent rows.
Older rows can be safely deleted. Run periodically (e.g. daily cron). Not wired yet.

Usage:
  IDEMPOTENCY_WINDOW_HOURS=72 python tooling/scripts/purge_old_idempotency_claims.py

Requires DATABASE_URL or DB_SECRET_ARN.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))


def _get_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    arn = os.environ.get("DB_SECRET_ARN")
    if not arn:
        raise ValueError("DATABASE_URL or DB_SECRET_ARN required")
    import subprocess

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
    hours = int(os.environ.get("IDEMPOTENCY_WINDOW_HOURS", "72"))
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    cutoff_str = cutoff.isoformat().replace("+00:00", "Z")

    import psycopg2

    conn = psycopg2.connect(_get_url())
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM data_plane.idempotency_claims
                WHERE created_at < %s::timestamptz
                RETURNING source_vendor, idempotency_key
                """,
                (cutoff_str,),
            )
            deleted = cur.rowcount
        conn.commit()
        print(f"Purged {deleted} idempotency_claims row(s) older than {hours}h (cutoff {cutoff_str})")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
