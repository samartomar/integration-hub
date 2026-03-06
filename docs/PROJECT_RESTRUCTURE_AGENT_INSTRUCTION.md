# Project Restructure – Agent Implementation Instruction

**Branch:** `feature/project-restructure`  
**Objective:** Restructure the Integration Hub repository to the agreed layout. Develop branch and pipeline remain unchanged; all work happens on this branch.

---

> **READ THIS FIRST:** After every phase, you MUST: (1) update all comments and path references, (2) run tests, (3) run lint, (4) validate functionality where applicable. Do not proceed to the next phase until the current one passes. At the end, run the full Verification Checklist. The restructure is not complete until all verification passes.

---

## Agent Workflow (MANDATORY – Follow After Every Phase)

For each phase, the agent **MUST**:

1. **Implement** the phase changes.
2. **Update comments and docs** – Any file that references old paths (e.g. `frontend/`, `backend/lambda`, `config/`) must have its comments, docstrings, and README text updated to the new paths. Search for old path strings and fix them.
3. **Run tests** – Execute `pytest tests/ -v` (or equivalent). All tests must pass before proceeding.
4. **Run lint** – Execute `ruff check` and `mypy infra`. Fix any errors.
5. **Validate functionality** – After phases that affect runnable code:
   - **Phase 3 (frontend):** `npm run dev:admin`, `npm run dev:partners` – both must start without errors.
   - **Phase 4 (backend):** `make local-up` (or `make local-sync-db`) and start the local API – must respond at /health.
   - **Phase 6 (infra):** `cdk synth` – must succeed.
   - **Phase 5 (tooling):** Manually run key buildspec commands (pip install, npm install in new paths) – must succeed.
6. **Do not proceed** to the next phase until the current phase passes all of the above.
7. **At the end** – Full verification (see Verification Checklist).

---

## Comments and Path References to Update

The agent **must search and update** these references throughout the codebase:

| Old reference | New reference |
|---------------|---------------|
| `frontend/` | `apps/web-cip/` |
| `frontend-vendor/` | `apps/web-partners/` |
| `frontend-shared/` | `packages/ui-shared/` |
| `backend/lambda` | `apps/api` or `apps/api/src` |
| `backend/local_api` | `apps/api/local` |
| `lambdas/ai_tool` | `apps/api/src/ai` |
| `lambdas/schema_init` | `apps/api/src/schema` |
| `config/` (when meaning env-config) | `packages/env-config/` |
| `layers/` | `packages/lambda-layers/` |
| `ai/` | `packages/bedrock-assets/` |
| `scripts/` | `tooling/scripts/` |
| `buildspec` location | `tooling/pipelines/` |

**Where to search:** All `.py`, `.ts`, `.tsx`, `.json`, `.yml`, `.yaml`, `.md` files, `.cursor/rules/*.mdc`.

---

## Target Structure (Final)

```
py-poc/
├── apps/
│   ├── web-cip/              # Admin UI (formerly frontend)
│   ├── web-partners/         # Vendor UI (formerly frontend-vendor)
│   └── api/                  # Backend (formerly backend + lambdas)
│       ├── alembic.ini       # Alembic config
│       ├── migrations/       # Alembic version files & env.py
│       ├── src/
│       │   ├── execute/      # routing logic, handler, tests
│       │   ├── registry/     # registry logic, handler, tests
│       │   ├── vendor/       # vendor_registry, onboarding
│       │   ├── audit/        # audit logging
│       │   ├── ai/           # ai_gateway, ai_tool
│       │   ├── schema/       # schema_init Lambda ONLY
│       │   └── shared/       # canonical_error, observability, auth guards
│       └── local/            # FastAPI dev server & mocks
│
├── packages/
│   ├── ui-shared/            # Shared React components (formerly frontend-shared)
│   ├── bedrock-assets/       # Prompts, tool schemas (formerly ai/)
│   ├── lambda-layers/        # integrationhub-common (formerly layers/)
│   ├── build-config/         # TS, Lint, Prettier (Dev dependencies)
│   └── env-config/           # env-config.json, naming (formerly config/)
│
├── tooling/
│   ├── pipelines/            # buildspec-*.yml
│   └── scripts/             # seed_local, load_env_config, etc.
│
├── infra/                    # CDK (unchanged location)
├── ephemeral/                # Developer ephemeral configs (config/*.json)
├── e2e/                      # Playwright/Cypress cross-app tests (if any)
├── app.py
├── cdk.json
├── pyproject.toml
├── package.json
├── docker-compose.yml
├── Makefile
└── ...
```

---

## Current → Target Mapping

| Current | Target |
|---------|--------|
| `frontend/` | `apps/web-cip/` |
| `frontend-vendor/` | `apps/web-partners/` |
| `frontend-shared/` | `packages/ui-shared/` |
| `backend/lambda/` | `apps/api/src/` (split by domain) |
| `backend/local_api/` | `apps/api/local/` |
| `backend/shared/` | `apps/api/src/shared/` |
| `lambdas/ai_tool/` | `apps/api/src/ai/` (merge with ai_gateway) |
| `lambdas/schema_init/` | `apps/api/src/schema/` |
| `migrations/` | `apps/api/migrations/` |
| `ai/` | `packages/bedrock-assets/` |
| `layers/integrationhub-common/` | `packages/lambda-layers/integrationhub-common/` |
| `config/` | `packages/env-config/` |
| `buildspec-*.yml` | `tooling/pipelines/` |
| `scripts/` | `tooling/scripts/` |
| `tests/` | Split: domain tests in `apps/api/src/*/tests/`; e2e in `e2e/` |

---

## Handler Preservation (CRITICAL)

**Lambda handler strings in CDK must not change.** AWS Lambda expects exact module paths.

| Lambda | Current Handler | Must Remain |
|--------|-----------------|-------------|
| routing | `routing_lambda.handler` | Same – keep `routing_lambda.py` or create thin wrapper |
| registry | `registry_lambda.handler` | Same |
| audit | `audit_lambda.handler` | Same |
| vendor_registry | `vendor_registry_lambda.handler` | Same |
| onboarding | `onboarding_lambda.handler` | Same |
| endpoint_verifier | `endpoint_verifier_lambda.handler` | Same |
| jwt_authorizer | `jwt_authorizer.handler` | Same |
| ai_gateway | `ai_gateway_lambda.handler` | Same |
| ai_tool | `handler.handler` (lambdas/ai_tool) | Same |
| schema_init | `handler.on_event` | Same |

**Approach:** Create thin handler modules at the package root (or in a `handlers/` dir) that delegate to domain modules. The handler file name (e.g. `routing_lambda.py`) must stay so CDK's `handler="routing_lambda.handler"` works.

---

## Implementation Order

### Phase 1: Create new structure (folders only)
- Create `apps/`, `packages/`, `tooling/`, `ephemeral/`, `e2e/` directories
- Create subdirs: `apps/web-cip`, `apps/web-partners`, `apps/api`, etc.

### Phase 2: Move packages (least dependencies first)
1. `packages/bedrock-assets/` ← `ai/` (agent-system-prompt.txt, tool-schema.json, list-operations-schema.json)
2. `packages/lambda-layers/integrationhub-common/` ← `layers/integrationhub-common/`
3. `packages/env-config/` ← `config/` (env-config.json, env-config.example.json, env-config.prod.json)
4. `packages/ui-shared/` ← `frontend-shared/`
5. Create `packages/build-config/` with shared tsconfig, eslint, prettier (extract or create)

### Phase 3: Move frontend apps
1. `apps/web-cip/` ← `frontend/` (git mv)
2. `apps/web-partners/` ← `frontend-vendor/` (git mv)
3. Update `package.json` in web-cip and web-partners: `"ui-shared": "file:../../packages/ui-shared"`
4. Update `vite.config.ts` paths in web-partners: `../ui-shared` instead of `../frontend-shared`
5. Root `package.json`: workspaces `["apps/*", "packages/*"]`, update dev scripts

### Phase 4: Move backend (most complex)
1. Create `apps/api/` structure
2. Move `migrations/` → `apps/api/migrations/`
3. Move `alembic.ini`, `env.py` (if at migrations root) → `apps/api/`
4. Split `backend/lambda/` by domain:
   - `execute/` ← routing_lambda, routing/
   - `registry/` ← registry_lambda
   - `vendor/` ← vendor_registry_lambda, onboarding_lambda
   - `audit/` ← audit_lambda
   - `ai/` ← ai_gateway_lambda + lambdas/ai_tool content
   - `schema/` ← lambdas/schema_init
   - `shared/` ← canonical_error, observability, admin_guard, etc.
5. Create thin handler modules (e.g. `routing_lambda.py`) that import from domains
6. Move `backend/local_api/` → `apps/api/local/`
7. Update `apps/api/local/app.py` paths and sys.path

### Phase 5: Move tooling
1. `tooling/pipelines/` ← buildspec-build.yml, buildspec-migrate.yml, buildspec-migrate-prod.yml
2. `tooling/scripts/` ← scripts/* (seed_local, load_env_config, run_migrations, etc.)
3. Update buildspec paths: `apps/api`, `apps/web-cip`, `apps/web-partners`, `packages/ui-shared`, `packages/env-config`, `packages/lambda-layers`, `packages/bedrock-assets`

### Phase 6: Update infra (CDK)
1. `infra/env_config.py`: config path → `packages/env-config/` or root `packages/env-config/`
2. `infra/stacks/data_plane_stack.py`: 
   - `backend/lambda` → `apps/api` (handler code path)
   - `lambdas/ai_tool` → `apps/api/src/ai` or preserve structure
   - `layers/integrationhub-common` → `packages/lambda-layers/integrationhub-common`
   - `ai/` → `packages/bedrock-assets`
3. `infra/stacks/database_stack.py`: schema_init path → `apps/api/src/schema` or wherever handler lives
4. Update `_REPO_ROOT` relative paths throughout

### Phase 7: Update tests
1. Move `tests/` content to `apps/api/src/*/tests/` by domain, or keep `tests/` at root with updated import paths
2. Update `sys.path` in test files to point to new locations
3. Update pytest config if needed

### Phase 8: Update all other references
- Dockerfile.local (if references backend)
- amplify.yml (appRoot)
- .cursor/rules
- Docs (README, ARCHITECTURE, etc.)
- Root package.json, pyproject.toml

### Phase 9: Ephemeral
- Create `ephemeral/config/` with `README.md` explaining `{developer}.json` format

---

## Files That MUST Be Updated (Checklist)

- [ ] `infra/stacks/data_plane_stack.py` – all path refs
- [ ] `infra/stacks/database_stack.py` – schema_init path
- [ ] `infra/env_config.py` – config dir
- [ ] `buildspec-build.yml` (in tooling/pipelines)
- [ ] `buildspec-migrate.yml`
- [ ] `buildspec-migrate-prod.yml`
- [ ] `app.py` – CDK (likely no changes)
- [ ] `apps/web-cip/package.json` – ui-shared path
- [ ] `apps/web-partners/package.json` – ui-shared path
- [ ] `apps/web-partners/vite.config.ts` – alias paths
- [ ] `apps/api/local/app.py` – sys.path, imports
- [ ] Root `package.json` – workspaces, scripts
- [ ] `docker-compose.yml` – if needed
- [ ] `Makefile` – if references backend/frontend
- [ ] `scripts/load_env_config.py` → `tooling/scripts/` – update config path
- [ ] `scripts/seed_local.py` → `tooling/scripts/` – update paths
- [ ] All test files – sys.path, imports
- [ ] `cdk.json` – if app path changes
- [ ] `.gitignore` – add `ephemeral/config/*.json` if dev configs should be gitignored (but commit ephemeral/ structure and README)

---

## Verification Checklist (Full – Run Before Declaring Done)

The agent must run and confirm **all** of the following before considering the restructure complete:

| # | Command / Action | Expected Result |
|---|------------------|-----------------|
| 1 | `pytest tests/ -v` | All tests pass |
| 2 | `ruff check infra apps tooling packages` (or per-project paths) | No errors |
| 3 | `mypy infra` | No errors |
| 4 | `cd apps/web-cip && npm install && npm run build` | Build succeeds |
| 5 | `cd apps/web-partners && npm install && npm run build` | Build succeeds |
| 6 | `cdk synth` | Synth succeeds, no path errors |
| 7 | `make local-up` (or equivalent) | Docker starts, DB initializes |
| 8 | Start local API (e.g. `uvicorn apps.api.local.app:app` or adjusted path) | Server starts, `/health` returns 200 |
| 9 | `make local-health` (if exists) or `curl http://localhost:8080/health` | Returns healthy response |
| 10 | Grep for old paths (`frontend/`, `backend/lambda`, etc.) in code and docs | No stale references (or document intentional ones) |

---

## Per-Phase Verification (Run After Each Phase)

| Phase | Verify |
|-------|--------|
| 1 | Directories exist |
| 2 | Packages moved; CDK/infra paths to bedrock-assets, lambda-layers, env-config work |
| 3 | `npm install` and `npm run build` in web-cip, web-partners succeed |
| 4 | `pytest tests/` passes; local API starts and responds |
| 5 | Buildspec commands run with new paths |
| 6 | `cdk synth` succeeds |
| 7 | All tests pass; imports resolve |
| 8 | No broken links or references in docs |
| 9 | ephemeral/config/ exists with README |

---

## Validate Each Functionality

When the local API is running, the agent should **smoke-test** that core flows work:

1. **Health:** `curl http://localhost:8080/health` → 200 OK
2. **Registry readiness:** `curl http://localhost:8080/v1/registry/readiness` (may need auth or bypass) – no 500
3. **Execute** (if mock available): `POST /v1/execute` with minimal payload – no import/runtime errors

If any of these fail, **fix before proceeding**. Do not assume “it will work in AWS” – local must work first.

---

## Branch Strategy

- **develop** – unchanged; continues to deploy via existing pipeline
- **feature/project-restructure** – all restructure work; deploy and verify here before merging
- After merge to develop, pipeline will use new structure

---

## Risk Mitigation

1. Use `git mv` for moves to preserve history
2. Preserve Lambda handler strings – no CDK handler changes
3. Run full test suite after each phase
4. Keep backend package name `backend` or migrate to `hub`; update imports consistently

---

## References

- Config schema: `config/env-config.example.json` (will move to `packages/env-config/`)
- CDK stacks: `infra/stacks/data_plane_stack.py`, `database_stack.py`, `portal_stack.py`
- Rules: `.cursor/rules/00-index.mdc`, `.cursor/rules/platform/01-infra-cicd.mdc`
