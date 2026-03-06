#!/usr/bin/env python3
"""Initialize local DB: run migrations + seed. Use with docker-compose or local Postgres.

Requires DATABASE_URL or (PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE).
Example: DATABASE_URL=postgresql://hub:hub@localhost:5434/hub python tooling/scripts/local_db_init.py
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import urllib.parse


def _db_url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("DB_URL")
    if url:
        return url
    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("PGPORT", "5434")
    user = os.environ.get("PGUSER", "hub")
    pw = os.environ.get("PGPASSWORD", "hub")
    db = os.environ.get("PGDATABASE", "hub")
    pw_enc = urllib.parse.quote(str(pw), safe="")
    return f"postgresql://{user}:{pw_enc}@{host}:{port}/{db}"


def _run_migrations(url: str) -> int:
    return subprocess.run(
        [sys.executable, "tooling/scripts/run_migrations.py"],
        env={**os.environ, "DATABASE_URL": url},
    ).returncode


def _run_seed() -> int:
    return subprocess.run([sys.executable, "tooling/scripts/seed_local.py"]).returncode


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local DB migrations and/or seed.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--migrate-only",
        action="store_true",
        help="Run migrations only (skip seed).",
    )
    group.add_argument(
        "--seed-only",
        action="store_true",
        help="Run seed only (skip migrations).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    url = _db_url()
    os.environ["DATABASE_URL"] = url
    os.environ["DB_URL"] = url

    # Default behavior keeps compatibility: run migrations then seed.
    run_migrations = not args.seed_only
    run_seed = not args.migrate_only

    if run_migrations:
        rc = _run_migrations(url)
        if rc != 0:
            return rc
    if run_seed:
        rc = _run_seed()
        if rc != 0:
            return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
