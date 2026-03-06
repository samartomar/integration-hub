# Cursor Execution Instructions – Dev Setup

## Purpose

This document defines how Cursor (or any automated agent) should execute dev setup and validation steps, with explicit confirmation before making changes.

## Confirmation gate

Before running any command that:

- Modifies the filesystem (create/delete files, install packages)
- Starts services (Docker, local API, etc.)
- Writes to the database (migrations, seeds)
- Changes environment variables or `.env` files

**The agent MUST:**

1. Show the user the exact commands it intends to run
2. Ask: "Confirm before executing? (y/n)"
3. Proceed only after explicit user confirmation (y/yes)

## Safe commands (no confirmation required)

- `git status`, `git diff`
- `ls`, `pwd`, `head`, `tail` (read-only)
- `rg` / `grep` (read-only search)
- `read_file` / `codebase_search` (read-only)
- `pytest tests/` (if tests are read-only and don't mutate state)

## Commands that require confirmation

- `npm install`, `pip install`
- `docker-compose up`, `docker run`
- `cdk deploy`, `cdk synth`
- `alembic upgrade`, `alembic revision`
- `python tooling/scripts/seed_local.py`
- Any script that writes to `.env`, `localStorage`, or DB

## Dev setup sequence (reference)

When user requests "run dev setup", execute in order:

1. `docker-compose up -d postgres` → **Confirm**
2. `alembic upgrade head` (or equivalent) → **Confirm**
3. `python tooling/scripts/seed_local.py` → **Confirm**
4. `make local-up` or `uvicorn apps.api.local.app:app --host 0.0.0.0 --port 8080` → **Confirm** (background)

Always output the command first, then wait for confirmation.

## Agent prompt

When acting on this document, include this in your reasoning:

> "I am following docs/security/CURSOR_EXECUTE.md. Commands that modify state require user confirmation before execution."
