#!/usr/bin/env python3
"""Verify DB is at Alembic head (no pending migrations).

Usage: DATABASE_URL=... python tooling/scripts/check_migrations_at_head.py
Exits 0 if current == head, 1 otherwise.
"""
from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    url = os.environ.get("DATABASE_URL") or os.environ.get("DB_URL")
    if not url:
        print("Error: DATABASE_URL or DB_URL required", file=sys.stderr)
        return 1
    os.environ["DATABASE_URL"] = url
    os.environ["DB_URL"] = url

    r_cur = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "apps/api/alembic.ini", "current"],
        capture_output=True,
        text=True,
        env={**os.environ, "DATABASE_URL": url},
    )
    r_head = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "apps/api/alembic.ini", "heads"],
        capture_output=True,
        text=True,
        env={**os.environ, "DATABASE_URL": url},
    )
    if r_cur.returncode != 0 or r_head.returncode != 0:
        print("Error: alembic current or heads failed", file=sys.stderr)
        return 1

    # alembic current: "v50 (head)" or "v50" -> take first token (revision id)
    current = ((r_cur.stdout or "").strip().split() or [""])[0]
    # alembic heads: "v50 (head)" or "v50" -> take first token
    head_line = (r_head.stdout or "").strip().split("\n")[0] or ""
    head = head_line.split()[0] if head_line else ""

    if not current:
        print("Error: DB has no revision (run alembic upgrade head)", file=sys.stderr)
        return 1
    if current != head:
        print(f"Error: DB at {current}, head is {head} (run alembic upgrade head)", file=sys.stderr)
        return 1
    print(f"OK: DB at head ({current})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
