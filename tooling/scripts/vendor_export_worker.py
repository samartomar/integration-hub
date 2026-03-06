#!/usr/bin/env python3
"""
Vendor export job worker - stub. Picks QUEUED jobs, logs what would be exported, updates status.

TODO: Implement actual S3 write. Export query requirements (see docs/VENDOR_EXPORTS.md):
- Time-bounded: created_at >= from_ts AND created_at <= to_ts (enables partition pruning).
- Vendor-scoped: vendor_code = job.vendor_code.
- Avoid full-table scan across all partitions.
- Use batched/streaming reads when writing to S3.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
from pathlib import Path

# Add apps/api/src/lambda to path for shared DB helpers
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
    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = psycopg2.connect(_get_url())
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, vendor_code, export_type, from_ts, to_ts
                FROM data_plane.vendor_export_jobs
                WHERE status = 'QUEUED'
                ORDER BY created_at ASC
                LIMIT 10
                """
            )
            jobs = cur.fetchall()
        for job in jobs:
            job_id = job["id"]
            vendor = job["vendor_code"]
            export_type = job["export_type"]
            from_ts = job["from_ts"]
            to_ts = job["to_ts"]
            print(f"Would export: id={job_id} vendor={vendor} type={export_type} from={from_ts} to={to_ts}")
            # TODO: Real export query goes here. CRITICAL:
            # - Use created_at >= from_ts AND created_at <= to_ts (time-bounded, partition pruning).
            # - Filter by vendor_code (vendor-scoped).
            # - Avoid scanning all partitions; created_at range prunes non-matching partitions.
            # - Use batched/streaming reads when writing to S3 (e.g. server-side cursor, COPY TO).
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE data_plane.vendor_export_jobs
                    SET status = 'FAILED', updated_at = now(), completed_at = now()
                    WHERE id = %s::uuid
                    """,
                    (str(job_id),),
                )
        conn.commit()
        print(f"Processed {len(jobs)} job(s) (stub: all marked FAILED)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
