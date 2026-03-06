#!/usr/bin/env python3
"""Run Alembic migrations against Aurora PostgreSQL.

Resolves DATABASE_URL from:
  - DATABASE_URL (if set directly)
  - DB_SECRET_ARN + DB_HOST + DB_PORT + DB_NAME (CodeBuild/pipeline context)

Usage:
  python tooling/scripts/run_migrations.py

Env (when DATABASE_URL not set):
  DB_SECRET_ARN  - Secrets Manager ARN for DB credentials
  DB_HOST        - Aurora cluster endpoint (from DatabaseStack)
  DB_PORT        - Default 5432
  DB_NAME        - Default integrationhub
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.parse


def _resolve_db_url() -> str:
    """Build DATABASE_URL from env or Secrets Manager."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    arn = os.environ.get("DB_SECRET_ARN")
    if not arn or arn == "None":
        raise ValueError(
            "DATABASE_URL or DB_SECRET_ARN required. "
            "For CodeBuild: DatabaseStack must be deployed first (provides SecretArn, Endpoint)."
        )
    result = subprocess.run(
        [
            "aws", "secretsmanager", "get-secret-value",
            "--secret-id", arn,
            "--query", "SecretString",
            "--output", "text",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to fetch secret: {result.stderr or result.stdout}")
    secret = json.loads(result.stdout)
    user = secret.get("username") or secret.get("user", "clusteradmin")
    pw = secret.get("password", "")
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    dbname = secret.get("dbname") or secret.get("database") or os.environ.get("DB_NAME", "integrationhub")
    pw_enc = urllib.parse.quote(str(pw), safe="")
    return f"postgresql://{user}:{pw_enc}@{host}:{port}/{dbname}"


def main() -> int:
    url = _resolve_db_url()
    os.environ["DATABASE_URL"] = url
    script_dir = os.path.dirname(os.path.abspath(__file__))
    tooling_dir = os.path.dirname(script_dir)
    repo_root = os.path.dirname(tooling_dir)
    api_dir = os.path.join(repo_root, "apps", "api")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        env={**os.environ, "DATABASE_URL": url},
        cwd=api_dir,
    )
    if result.returncode != 0:
        print("ERROR: alembic upgrade head failed", file=sys.stderr)
        return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
