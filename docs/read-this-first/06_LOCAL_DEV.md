# Local Development

Run the Integration Hub locally without AWS. Use this for day-to-day development.

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python 3.11+ | `pyproject.toml` requires `>=3.11` |
| Node.js (LTS) | For apps/web-partners; `npm install` in `apps/web-partners/` |
| Docker | For `docker-compose` (db, hub-api) |
| Make | For `make local-up`, `make local-sync-db`, etc. |
| Auth0 | Recommended for vendor/admin portal and API calls (JWT with `bcpAuth` claim) |

If using Cursor or an AI agent to run setup commands, see [docs/security/CURSOR_EXECUTE.md](../security/CURSOR_EXECUTE.md) before executing commands that modify state.

---

## Quick Start

```bash
# 1. Install deps
pip install -e ".[dev]"

# 2. Start everything (DB + hub-api, migrations, seed)
make local-up

# 3. Verify
make local-health
# Or: curl http://localhost:8080/health

# 4. Stop and clean
make local-down
```

---

## Stack (Layer B)

| Component | Purpose |
|-----------|---------|
| Docker Postgres | Local database |
| hub-api (Uvicorn) | HTTP API wrapping Lambda handlers |
| Local portals | Vite (apps/web-partners, apps/web-cip) |
| Auth0 dev tenant or local JWT | JWT auth |

**Invariant:** Local behavior must match prod semantics (JWT auth, same execute pipeline).

---

## Make Targets

| Target | Action |
|--------|--------|
| `make local-up` | Start DB + hub-api, run migrations + seed |
| `make local-down` | Stop containers, remove volumes |
| `make local-sync-db` | Apply migrations + seed (idempotent, no container changes) |
| `make local-health` | Curl health endpoints |
| `make local-logs` | Follow Docker logs |
| `make install-ui` | Install UI deps (npm install) |
| `make dev-admin` | Start Admin portal (apps/web-cip) on port 5173 |
| `make dev-partners` | Start Vendor portal (apps/web-partners) on port 5174 |
| `make build-ui` | Build both Admin and Vendor portals |

---

## Endpoints (Local)

| Path | Method | Auth | Handler |
|------|--------|------|---------|
| `/v1/execute` | POST | JWT (`Authorization: Bearer <token>`) | routing_lambda |
| `/v1/ai/execute` | POST | JWT (`Authorization: Bearer <token>`) | ai_gateway_lambda |
| `/v1/vendor/*` | * | JWT (`Authorization: Bearer <token>`) | vendor_registry_lambda |
| `/v1/registry/*` | * | JWT (local: AUTH_BYPASS) | registry_lambda |
| `/v1/audit/*` | * | JWT (local: AUTH_BYPASS) | audit_lambda |
| `/health` | GET | — | Health check |

---

## Seed Data (Local)

| Item | Value |
|------|-------|
| Vendors | LH001 (Vendor A), LH002 (Vendor B) |
| Operations | GET_RECEIPT, GET_WEATHER |
| JWT claim | `bcpAuth=LH001` for vendor identity in local/dev tokens |
| Allowlist | LH001 → LH002 for GET_RECEIPT (OUTBOUND) |
| Endpoint | LH002 GET_RECEIPT → default demo receipt URL |

---

## Environment Variables

| Variable | Description | Local default |
|----------|-------------|---------------|
| DB_URL | Postgres connection | postgresql://hub:hub@db:5432/hub |
| AUTH_BYPASS | Inject mock authorizer for registry/audit/admin (local dev) | true (in docker-compose) |
| USE_BEDROCK | Call Bedrock for AI | false |
| RUN_ENV | local / dev / prod | local |

---

## Run API Without Docker

If Postgres runs on host (e.g. port 5434):

```bash
export DB_URL=postgresql://hub:hub@localhost:5434/hub
export AUTH_BYPASS=true
export USE_BEDROCK=false

python tooling/scripts/local_db_init.py   # migrations + seed (once)
uvicorn apps.api.local.app:app --host 0.0.0.0 --port 8080
```

---

## Quick Execute Test (JWT)

```bash
# Runtime API (vendor source derived from JWT bcpAuth claim)
curl -X POST http://localhost:8080/v1/execute \
  -H "Authorization: Bearer <vendor-jwt-with-bcpAuth>" \
  -H "Content-Type: application/json" \
  -d '{"targetVendor":"LH002","operation":"GET_RECEIPT","parameters":{"transactionId":"123"}}'
```

Expected: `{"status":"OK","receiptId":"R-123"}` (or similar) when provider endpoint is reachable.

---

## Postman

The `postman/` folder is gitignored. Generate it first: `python tooling/scripts/generate_postman.py`

1. Import `postman/Integration-Hub-POC.postman_collection.json`
2. Import `postman/Integration-Hub-POC-Local.postman_environment.json`
3. Select "Integration Hub - Local" in environment dropdown
4. Base URLs → `http://localhost:8080`; configure JWT bearer token in Authorization

See [POSTMAN.md](POSTMAN.md) for full instructions (AWS env, get-postman-urls script).

---

## Common Issues

| Issue | Fix |
|-------|-----|
| Port 5434 or 8080 in use | Stop conflicting services; or edit `docker-compose.yml` to use different ports |
| `make local-up` hangs | DB may take time to become ready. Try `make local-sync-db` manually after containers start |
| Execute returns `VENDOR_NOT_FOUND` | Run `make local-sync-db` and verify JWT contains `bcpAuth` claim (e.g. `LH001`) |
| Execute returns `ENDPOINT_NOT_FOUND` | Seed provisions LH002 GET_RECEIPT endpoint URL. Check `control_plane.vendor_endpoints` and reseed via `make local-sync-db` |
| Execute returns `ALLOWLIST_DENIED` | Seed permits LH001→LH002 for GET_RECEIPT. Check `vendor_operation_allowlist` |
| `connection refused` to DB when running API on host | Use `localhost:5434` (host port) not `db:5432`; set `DB_URL=postgresql://hub:hub@localhost:5434/hub` |
| Admin 403 on login | Admin needs its own Auth0 SPA with `http://localhost:5173/callback`. See [11_TROUBLESHOOTING](11_TROUBLESHOOTING.md). |
| Vendor portal CORS / Auth0 redirect | Add `http://localhost:5174` to Auth0 **Vendor** SPA redirect URIs |
| 403 Forbidden on /v1/registry/* or /v1/audit/* | Ensure `AUTH_BYPASS=true` for hub-api (included in docker-compose). Local API has no JWT authorizer; AUTH_BYPASS injects mock authorizer. |

For more, see [11_TROUBLESHOOTING.md](11_TROUBLESHOOTING.md).

---

## Full Reference

See [11_TROUBLESHOOTING.md](11_TROUBLESHOOTING.md) for common issues.

---

Next: [07_FIRST_WEEK_PLAN.md](07_FIRST_WEEK_PLAN.md)
