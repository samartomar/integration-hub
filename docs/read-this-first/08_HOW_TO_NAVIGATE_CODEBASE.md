# How to Navigate the Codebase

Where to find things in the Integration Hub repo.

---

## Top-Level Layout

```
py-poc/
├── apps/
│   ├── api/           # Backend API
│   │   ├── src/lambda/  # Lambda handlers (used by AWS + local)
│   │   ├── local/       # FastAPI app for local dev
│   │   └── migrations/  # Alembic DB migrations
│   ├── web-cip/       # Admin portal
│   └── web-partners/  # Vendor portal (React + Vite)
├── packages/
│   ├── ui-shared/     # Shared frontend components/API clients
│   ├── env-config/    # Environment config
│   └── lambda-layers/ # integrationhub-common layer
├── tooling/
│   ├── scripts/       # local_db_init, run-migrations, seed, generate_postman, etc.
│   └── local-dev/     # Local development container assets
├── infra/             # CDK stacks
├── postman/           # Postman (gitignored; run python tooling/scripts/generate_postman.py)
├── tests/             # Pytest tests
├── docs/              # Documentation
├── .cursor/rules/     # Cursor rule files
├── Makefile           # local-up, local-down, local-sync-db, etc.
├── docker-compose.yml # Local Docker stack
└── pyproject.toml     # Python project config
```

---

## Backend Lambda (`apps/api/src/lambda/`)

| File | Purpose |
|------|---------|
| `routing_lambda.py` | Execute pipeline: validate, allowlist, contract, mapping, endpoint, downstream call |
| `vendor_registry_lambda.py` | Vendor CRUD: endpoints, mappings, contracts, allowlist, change requests |
| `registry_lambda.py` | Admin CRUD: vendors, operations, allowlist, endpoints, approve/reject |
| `audit_lambda.py` | Read transactions, audit events |
| `ai_gateway_lambda.py` | AI execute: PROMPT (Bedrock) or DATA (execute + formatter) |
| `onboarding_lambda.py` | Vendor self-registration, API key issuance |
| `endpoint_verifier_lambda.py` | EventBridge `endpoint.upserted` → validate endpoint |
| `contract_utils.py` | `load_effective_contract`, `load_canonical_contract` |
| `endpoint_utils.py` | `load_effective_endpoint`, `EndpointNotFound` |
| `mapping_utils.py` | `resolve_effective_mapping` |
| `routing/transform.py` | `apply_mapping` – JSON transform logic |
| `canonical_error.py` | Error helpers: `auth_error`, `allowlist_denied`, `endpoint_not_found`, etc. |
| `jwt_auth.py` | JWT validation, `validate_jwt_and_map_vendor` |
| `vendor_identity.py` | `resolve_vendor_code`, `resolve_vendor_and_key_id` |
| `admin_guard.py` | `require_admin_secret` (JWT/admin role) for admin routes |
| `cors.py` | CORS header helpers |

---

## Local API (`apps/api/local/`)

| File | Purpose |
|------|---------|
| `app.py` | FastAPI app; routes map to Lambda handlers, no AWS |

Run: `uvicorn apps.api.local.app:app --host 0.0.0.0 --port 8080` (or `make local-up` for full Docker stack)

---

## Database

| Path | Purpose |
|------|---------|
| `apps/api/migrations/` | Alembic migrations; baseline schema is source of truth |
| `tooling/scripts/local_db_init.py` | Runs migrations + seed for local dev |
| `tooling/scripts/seed_local.py` | Seed data (vendors, operations, allowlist, etc.) |

**Schemas:** `control_plane.*`, `data_plane.*` – do not regenerate baseline.

---

## Frontend

| Path | Purpose |
|------|---------|
| `apps/web-partners/` | Vendor portal – operations, endpoints, mappings, allowlist, change requests |
| `packages/ui-shared/` | Shared components, API clients |
| Admin portal | `apps/web-cip` |

---

## Infra & CI/CD

| Path | Purpose |
|------|---------|
| `cdk/` or `infra/` | CDK app and stacks |
| `tooling/pipelines/buildspec-*.yml` | CodeBuild pipeline specs |
| `docker-compose.yml` | Local DB + hub-api |

---

## Tests

| Path | Purpose |
|------|---------|
| `tests/` | Pytest tests for routing, contracts, mappings, errors, etc. |

Run: `pytest tests/ -v`

---

## Rules (`.cursor/rules/`)

| File | When to open |
|------|--------------|
| `.cursor/rules/00-index.mdc` | Master index; use to find the right rule |
| `.cursor/rules/context/00-context.mdc` | High-level context |
| `.cursor/rules/security-identity/00-auth-federation.mdc` | Auth, JWT, vendor identity |
| `.cursor/rules/data-model/00-contracts.mdc` | Effective contract |
| `.cursor/rules/data-model/01-mappings.mdc` | Effective mapping, canonical pass-through |
| `.cursor/rules/data-model/02-endpoints.mdc` | Endpoint resolution |
| `.cursor/rules/governance/00-allowlist-access.mdc` | Allowlist, access matrix |
| `.cursor/rules/runtime/00-execute-runtime.mdc` | Execute pipeline steps |
| `.cursor/rules/runtime/01-ai-gateway.mdc` | AI Gateway modes |
| `.cursor/rules/platform/00-local-dev.mdc` | Local dev commands |
| `.cursor/rules/platform/01-infra-cicd.mdc` | CDK, pipelines, auto-wiring |
| `.cursor/rules/platform/02-custom-domains.mdc` | Domain layout |
| `.cursor/rules/product-controls/00-feature-gates.mdc` | Feature gates |
| `.cursor/rules/dev-support/00-seed-data.mdc` | Seed rules |
| `.cursor/rules/agent-rules/00-agent-constraints.mdc` | Agent constraints |
| `.cursor/rules/agent-rules/01-ai-formatter.mdc` | AI formatter behavior |
| `.cursor/rules/agent-rules/02-git-workflow.mdc` | Git workflow guidance |
| `.cursor/rules/strategy/00-vision.mdc` | Product vision |
| `.cursor/rules/strategy/01-future-roadmap.mdc` | Forward-looking guidance |

---

## Search Tips

- **"Where is load_effective_contract?"** → `apps/api/src/lambda/contract_utils.py`
- **"Where is allowlist checked?"** → `apps/api/src/lambda/routing_lambda.py` (inside validate_control_plane)
- **"Where is mapping applied?"** → `apps/api/src/lambda/routing/transform.py`
- **"Auth/JWT"** → `jwt_auth.py`, `vendor_identity.py`
- **"Error codes"** → `canonical_error.py`

---

Next: [09_RULES_GUIDE.md](09_RULES_GUIDE.md)
