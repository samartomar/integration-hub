# Troubleshooting

Common errors and how to fix them. See also [06_LOCAL_DEV.md](06_LOCAL_DEV.md) for local setup issues.

---

## Local Setup

### `make local-up` fails or hangs

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Port already in use | 5434 or 8080 occupied | Check `docker ps`; stop conflicting services or change ports in `docker-compose.yml` |
| DB not ready | hub-api starts before Postgres | Run `make local-sync-db` manually after containers are up; or wait for healthcheck retries |
| Build fails | Missing Dockerfile or context | Ensure `Dockerfile.local` exists; run from repo root |
| Permission denied | Docker not running or no access | Start Docker Desktop; ensure user is in `docker` group |

### `make local-health` returns errors

| Symptom | Fix |
|---------|-----|
| Connection refused to localhost:8080 | hub-api not running. Check `docker-compose ps`; view `docker-compose logs hub-api` |
| hub-api returns 500 | Migrations or seed failed. Run `make local-sync-db`; check logs for DB errors |
| 403 Forbidden on /v1/registry/* or /v1/audit/* | Local API injects mock authorizer when `RUN_ENV=local` or `AUTH_BYPASS=true`. Recreate containers: `make local-down` then `make local-up`. If running uvicorn directly, set `AUTH_BYPASS=true` or `RUN_ENV=local`. |

### Database connection errors

| Symptom | Fix |
|---------|-----|
| `connection refused` to db:5432 | Running API outside Docker? Use `localhost:5434` and `DB_URL=postgresql://hub:hub@localhost:5434/hub` |
| `relation "vendors" does not exist` | Migrations not run. Run `make local-sync-db` or `python tooling/scripts/local_db_init.py` |
| `password authentication failed` | Wrong creds. Default: user=hub, password=hub, db=hub |

---

## Execute / Runtime Errors

### `AUTH_ERROR` (401)

| Cause | Fix |
|-------|-----|
| **401 on AWS endpoints (Admin/Vendor portals)** | Frontend must request audience `urn:integrationhub:api`. `make dev-ui` / `dev-ui-aws` injects `VITE_AUTH0_AUDIENCE` by default. If still failing: ensure `.env.aws` or app `.env.local` has `VITE_AUTH0_AUDIENCE=urn:integrationhub:api`; **log out and log back in** to get a fresh token with the correct audience. |
| Missing Authorization (Runtime API) | Use JWT (Authorization: Bearer) for `/v1/execute`, `/v1/ai/execute` |
| Missing Authorization (vendor execute) | Use JWT (Authorization: Bearer) for `/v1/integrations/execute` |
| Invalid JWT | Ensure Auth0 config is correct; JWT has valid `iss`, `aud`, and vendor claim |
| JWT auth not configured | If using JWT, set `IDP_JWKS_URL`, `IDP_ISSUER`, `IDP_AUDIENCE` in env |

### `VENDOR_NOT_FOUND` (404)

| Cause | Fix |
|-------|-----|
| Vendor code from JWT not in DB | Ensure vendor exists in `control_plane.vendors`; run `make local-sync-db` for seed |
| Vendor code from JWT not in DB | Ensure vendor exists in `control_plane.vendors`; check `vendor_code` (or configured claim) |
| Wrong vendor in body | For `/v1/execute`, `sourceVendor` must exist; for `/v1/integrations/execute`, source comes from JWT |

### `ALLOWLIST_DENIED` / `ALLOWLIST_VENDOR_DENIED` (403)

| Cause | Fix |
|-------|-----|
| No allowlist rule for (source, target, operation) | Add rule via admin API or seed; e.g. LH001 → LH002 for GET_RECEIPT |
| Wrong flow direction | Allowlist uses `flow_direction` (OUTBOUND/INBOUND/BOTH); ensure rule matches the flow |
| Vendor inactive | Check `vendors.is_active = true` |

### `CONTRACT_NOT_FOUND` (404)

| Cause | Fix |
|-------|-----|
| No canonical contract for operation | Add canonical contract for the operation |
| No vendor contract and no canonical | Either add canonical or vendor-specific contract |
| Wrong operation code | Ensure operation exists in `control_plane.operations` |

### `ENDPOINT_NOT_FOUND` (404)

| Cause | Fix |
|-------|-----|
| No endpoint for (vendor, operation, direction) | Add `vendor_endpoints` row with `is_active = true` |
| Wrong flow direction | OUTBOUND = vendor as source; INBOUND = vendor as target. Endpoint must match |
| Endpoint inactive | Set `is_active = true` |
| provider endpoint not reachable | For local: verify seeded endpoint URL and network reachability |

### `SCHEMA_VALIDATION_FAILED` (400)

| Cause | Fix |
|-------|-----|
| Request body doesn't match effective contract | Check contract schema; ensure `value` has required fields (e.g. `txnId` for GET_RECEIPT) |
| Invalid JSON | Ensure `Content-Type: application/json` and valid JSON body |

### `MAPPING_FAILED` (400)

| Cause | Fix |
|-------|-----|
| Mapping template error | Check `vendor_operation_mappings`; validate Jinja/template syntax |
| Missing template variable | Ensure mapping inputs match contract outputs |

### `DOWNSTREAM_TIMEOUT` / `DOWNSTREAM_CONNECTION_ERROR`

| Cause | Fix |
|-------|-----|
| Vendor endpoint unreachable | For local GET_RECEIPT: verify URL in `vendor_endpoints` and provider availability |
| Wrong URL in endpoint config | Verify `vendor_endpoints.url` |
| Firewall / network | If calling external URL, check network access |
| Timeout too short | Increase `timeout_ms` in endpoint config (within limits) |

### `DOWNSTREAM_HTTP_ERROR` (502 / varies)

| Cause | Fix |
|-------|-----|
| Vendor returned 4xx/5xx | Check `error.details` for status and response body |
| Provider endpoint not implemented for operation | Use supported operations (e.g. GET_RECEIPT); provider may return errors for others |

---

## Frontend / Auth0

**Admin and Vendor use different Auth0 SPAs.** Each needs its own Application and Client ID. Do not reuse the same Client ID.

### Admin portal (web-cip) – 403 or won't log in

| Symptom | Fix |
|---------|-----|
| 403 on login or callback | Admin needs its **own** Auth0 SPA. Add both `http://localhost:5173` and `http://localhost:5173/callback` to Allowed Callback URLs (both required). Add `http://localhost:5173` to Allowed Logout URLs. Same pattern applies for Okta or other IdPs. |
| 403 on API calls after login | Verify `VITE_ADMIN_API_BASE_URL=http://localhost:8080` (not 8000). Local hub-api runs on 8080. |
| Wrong Auth0 app | Ensure `VITE_AUTH0_CLIENT_ID` in `apps/web-cip/.env.local` is the **Admin** SPA client ID (`d7xi8p9o...`), not the Vendor one. |

### Vendor portal (web-partners) – won't log in

| Symptom | Fix |
|---------|-----|
| Redirect URI mismatch | Add `http://localhost:5174` and `http://localhost:5174/callback` to Auth0 **Vendor** SPA redirect URIs |
| CORS errors | Ensure Auth0 allows your origin; check `Auth0ProviderWithConfig` domain/clientId |
| "Invalid state" | Clear cookies/localStorage; retry |

### Auth0 not configured

| Portal | Port | Auth0 setup |
|--------|------|------------|
| Admin | 5173 | Create SPA; add `http://localhost:5173/callback` to Allowed Callback URLs |
| Vendor | 5174 | Create SPA; add `http://localhost:5174/callback` to Allowed Callback URLs |

Set `VITE_AUTH0_DOMAIN`, `VITE_AUTH0_CLIENT_ID` in each app's `.env` or `.env.local`. Use the correct Client ID per portal.

---

## Pipelines / CDK

### Build fails in CodePipeline

| Symptom | Fix |
|---------|-----|
| `ruff` or `mypy` errors | Run `ruff check .` and `mypy` locally; fix before pushing |
| `pytest` failures | Run `pytest tests/ -v` locally |
| Missing .bundled | Build spec pre-bundles lambdas; check `tooling/pipelines/buildspec-build.yml` |

### Migrate fails

| Symptom | Fix |
|---------|-----|
| Alembic upgrade fails | Run migrations locally first; fix migration script |
| DB secret/host not found | Pipeline resolves from CloudFormation; ensure DatabaseStack outputs are correct |

---

## When to Get Help

- **DB schema questions** – Check `apps/api/migrations/` and baseline schema; do not regenerate.
- **Auth/JWT** – See `.cursor/rules/security-identity/00-auth-federation.mdc`; vendor identity comes from JWT only.
- **Execute pipeline** – See [05_RUNTIME_FLOW.md](05_RUNTIME_FLOW.md) and `.cursor/rules/runtime/00-execute-runtime.mdc`.
- **CURSOR_EXECUTE** – Before running commands that alter env/DB, see [docs/security/CURSOR_EXECUTE.md](../security/CURSOR_EXECUTE.md).

---

Back to [00_INDEX.md](00_INDEX.md)
