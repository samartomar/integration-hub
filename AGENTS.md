# AGENTS.md

## Cursor Cloud specific instructions

### Services overview

| Service | Port | How to start |
|---------|------|--------------|
| PostgreSQL | 5434 | `sudo pg_ctlcluster 16 main start` (pre-configured, user `hub`, DB `hub`) |
| Hub API (FastAPI) | 8080 | See "Starting the Hub API" below |
| Admin portal (web-cip) | 5173 | `cd apps/web-cip && npx vite --port 5173 --host 0.0.0.0` |
| Vendor portal (web-partners) | 5174 | `cd apps/web-partners && npx vite --port 5174 --host 0.0.0.0` |

### Starting the Hub API

```bash
DB_URL=postgresql://hub:hub@localhost:5434/hub \
DATABASE_URL=postgresql://hub:hub@localhost:5434/hub \
AUTH_BYPASS=true USE_BEDROCK=false RUN_ENV=local \
uvicorn apps.api.local.app:app --host 0.0.0.0 --port 8080
```

Use `AUTH_BYPASS=true` for local dev (no Okta). The runtime execute endpoint (`/v1/execute`) always validates the JWT bearer token directly; AUTH_BYPASS only injects a mock authorizer for registry/vendor/audit endpoints.

### DB migrations and seed

```bash
PGHOST=localhost PGPORT=5434 PGUSER=hub PGPASSWORD=hub PGDATABASE=hub \
DATABASE_URL=postgresql://hub:hub@localhost:5434/hub \
python3 tooling/scripts/local_db_init.py
```

Or use `make local-db-init` / `make local-sync-db` (same thing). The `python` command must point to `python3`.

### Lint and test commands

- **Python lint:** `ruff check .` (pre-existing warnings exist; config in `pyproject.toml`)
- **Python tests:** `PYTHONPATH=apps/api/src/lambda python3 -m pytest tests/` (set DB env vars as above). Note: `tests/test_routing_lambda.py` has a pre-existing syntax error and must be excluded with `--ignore`.
- **Frontend tests (admin):** `cd apps/web-cip && npx vitest run`
- **Frontend tests (vendor):** `cd apps/web-partners && npx vitest run` (1 pre-existing test failure in `VendorEndpointsConfigPage.test.tsx`)
- **Frontend build:** `cd apps/web-cip && npx vite build` / `cd apps/web-partners && npx vite build`
- **ESLint:** Not configured (no `eslint.config.js` exists); the `npm run lint` scripts will fail.

### Gotchas

- PostgreSQL listens on port **5434** (not default 5432) to match `docker-compose.yml` and `Makefile`.
- The `python` binary may not exist; always use `python3` or create a symlink.
- `~/.local/bin` must be on `PATH` for `uvicorn`, `pytest`, `ruff`, etc.
- Frontend apps each have their own `node_modules`; run `npm install` in `packages/ui-shared`, `apps/web-cip`, and `apps/web-partners` separately.
- The admin portal requires Okta config (`VITE_OKTA_*` env vars) to function fully. Without it, the portal shows an auth error page. The vendor portal renders in local mode without Okta.
