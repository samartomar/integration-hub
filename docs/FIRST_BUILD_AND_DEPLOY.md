# First Build and Deployment Plan

This document captures the current state of the Integration Hub build/deploy pipeline, issues found, fixes applied, and a checklist for a successful first build and deployment.

---

## Summary

| Area | Status | Notes |
|------|--------|--------|
| CDK synth | ✅ Passes | All stacks synthesize; Lambda bundling uses Docker or pre-bundle |
| Lambda pre-bundle (no Docker) | ✅ Passes | `.\tooling\scripts\bundle-lambdas.ps1` works on Windows |
| Admin portal (web-cip) build | ✅ Passes | After fixes below |
| Vendor portal (web-partners) build | ✅ Passes | After fixes below |
| Python test suite | ⚠️ 42 failures | 326 pass, 6 skip; failures block CI if run as-is |
| Deploy script | ✅ Ready | Use `USE_PREBUNDLED=1` when Docker is not available |

---

## Fixes Applied (for First Build)

The following changes were made so that **first build** succeeds locally and in CI (once tests are addressed or gated).

### 1. Admin portal (apps/web-cip)

- **vite.config.ts**  
  `test` is not on Vite’s default config type. Switched to Vitest’s config so `test` is recognized:
  - `import { defineConfig } from "vitest/config"` instead of `"vite"`.

- **MissionControlPage.test.tsx**  
  TypeScript did not recognize `.mock` on the mocked function. Use the typed mock:
  - `vi.mocked(endpointsApi.getMissionControlActivity).mock.calls.length` instead of `endpointsApi.getMissionControlActivity.mock.calls.length`.

### 2. Vendor portal (apps/web-partners)

- **ConfigNavCards.tsx**  
  `isActiveWhen` callbacks had parameter `p` with implicit `any`. Added explicit type:
  - `(p: string) => ...` for all four card definitions.

### 3. Python tests

- **tests/test_routing_lambda.py**  
  Removed stray commas that caused `SyntaxError` in three places:
  - Inside `_base_event(...)` call (line ~774).
  - Two more similar `_base_event(...)` calls (~2879, ~2958).

---

## Remaining Issues (to Address for Green CI)

These do not block a manual first deploy but **will fail** the Build stage if `pytest tests/` is run as in `buildspec-build.yml`.

### Test failure categories

1. **Vendor/registry API shape or routes (404/405)**  
   - `test_allowlist_change_requests.py`: expect 201/400, get 404.  
   - `test_vendor_change_requests.py`: expect 201/200/400, get 404 or 405.  
   - Likely route or handler path changes; align tests or API.

2. **Vendor registry Lambda API drift**  
   - Tests patch/mock `vendor_registry_lambda.is_feature_gated`, `_list_effective_vendor_contracts`, `_create_vendor_change_request`, or `socket`.  
   - These symbols are missing or renamed in the current Lambda module. Update mocks to match current `vendor_registry_lambda` API.

3. **Runtime execute (JWT)**  
   - `test_runtime_api_execute.py::test_runtime_execute_happy_path`: expects 200, gets 401 “JWT auth not configured”.  
   - Either configure JWT in test env or mock auth so the test does not require a real IdP.

4. **Repository / allowlist query semantics**  
   - `test_repository_queries.py`: “Target wildcard semantics are no longer used in runtime query” and `is_any_target` in SQL.  
   - Align test expectations with current runtime query (remove or update wildcard assertions).

5. **Vendor registry responses**  
   - Several tests expect 200/202 but get 500/503; some expect specific error codes (e.g. `ADMIN_API_UNAVAILABLE`) but get `DOWNSTREAM_ERROR`.  
   - Align mock or implementation with current error handling and status codes.

6. **Response shape drift**  
   - `test_vendor_auth_profile_diagnostics.py`: `KeyError: 'ok'`.  
   - `test_vendor_registry_my_operations_canonical.py`: `KeyError: 'effectiveMappingConfigured'`.  
   - Update tests or API to the current response schema.

7. **Catalog API signature**  
   - `test_vendor_registry_operations_catalog.py`: `_list_operations_catalog() got an unexpected keyword argument 'vendor_code'`.  
   - Update call site or function signature.

### Recommended next steps for CI

- Option A: Fix the failing tests and keep `pytest tests/` in the Build stage (preferred long-term).  
- Option B: Temporarily run only a subset of tests in CI (e.g. `pytest tests/ -k "not test_allowlist and not test_vendor_change"`) until full fix.  
- Option C: Add a “test” job that can fail without blocking deploy, until tests are fixed.

---

## First Build Checklist (local)

Use this to confirm a clean first build on your machine.

- [ ] **Python 3.11+** (recommended; project lists 3.11; 3.14 was used during validation).
- [ ] **Node.js 20+** and npm available.
- [ ] **Pip**: use `python -m pip` if `pip` is not on PATH.

```powershell
# 1. Repo root
cd e:\dev\hub

# 2. Python deps (CDK + app)
python -m pip install -r requirements.txt
python -m pip install -e ".[dev]"

# 3. CDK synth (uses Docker for Lambda assets if available)
npx aws-cdk synth
```

If CDK reports “Failed to bundle asset” (no Docker):

```powershell
.\tooling\scripts\bundle-lambdas.ps1
$env:USE_PREBUNDLED = "1"
npx aws-cdk synth
```

- [ ] **UI: install and build**

```powershell
cd packages\ui-shared && npm install && cd ..\..
cd apps\web-cip && npm install && npm run build && cd ..\..
cd apps\web-partners && npm install && npm run build && cd ..\..
```

- [ ] **Optional: run Python tests**  
  Expect 42 failures until the issues above are fixed:

```powershell
python -m pytest tests/ -q --tb=line
```

---

## First Deployment Checklist

Deploy in order. Use the same account/region as your CDK bootstrap.

### Prerequisites

- [ ] AWS CLI configured (credentials and region).
- [ ] CDK bootstrapped: `npx aws-cdk bootstrap aws://ACCOUNT_ID/REGION`.
- [ ] If no Docker: run `.\tooling\scripts\bundle-lambdas.ps1` and set `USE_PREBUNDLED=1`.

### Deploy order (no PipelineStack)

Deploy core stacks first (PipelineStack and ProdPipelineStack can be added later):

```powershell
$env:USE_PREBUNDLED = "1"   # if not using Docker
.\tooling\scripts\deploy.ps1
```

The script deploys: **FoundationStack** → **DatabaseStack** → **OpsAccessStack** → **DataPlaneStack**.

If you hit export/import errors:

1. Deploy one stack at a time in that order.
2. Ensure the CDK bootstrap qualifier matches (`cdk.json`: `@aws-cdk/core:bootstrapQualifier`: `intghub`).

### Optional stacks (after core is healthy)

- **PortalStack**: requires `CustomDomainRoot` (and optionally `CustomDomainHostedZoneId`) in context or env (see `packages/env-config/env-config.json`). Deploy in **us-east-1** (ACM/CloudFront).
- **PipelineStack** / **ProdPipelineStack**: require GitHub connection ARN and repo; deploy when CI/CD is ready.

### Verify

- FoundationStack: outputs for VPC, etc.
- DatabaseStack: RDS or Aurora endpoint if applicable.
- DataPlaneStack: Admin API URL, Vendor API URL, Runtime API URL.
- Health: `curl <RuntimeApiUrl>/health` (and any auth required by the API).

---

## CI/CD (CodeBuild / CodePipeline)

- **buildspec-build.yml**: lint (ruff), mypy, **pytest**, then Lambda pre-bundle. Current pytest failures will fail this stage.
- **buildspec-deploy.yml**: runs `cdk deploy --all --require-approval never`.

For a first successful pipeline run:

1. Fix or gate the failing tests (see “Remaining Issues” above), or
2. Temporarily reduce test scope / allow test job to fail, then fix tests and re-enable.

---

## Environment and config

- **Env config**: `packages/env-config/env-config.json` (and optional `env-config.prod.json`). Overrides via CDK context (`-c`) or env vars (`ENVIRONMENT`, `CUSTOM_DOMAIN_ROOT`, `CUSTOM_DOMAIN_HOSTED_ZONE_ID`).
- **Python**: CI uses 3.11; local can be 3.11+.
- **Node**: 20 in CI; 20+ locally recommended.

---

## Quick reference

| Task | Command |
|------|--------|
| Synth | `npx aws-cdk synth` |
| Pre-bundle Lambdas (no Docker) | `.\tooling\scripts\bundle-lambdas.ps1` |
| Deploy core stacks | `$env:USE_PREBUNDLED="1"; .\tooling\scripts\deploy.ps1` |
| Build admin UI | `cd apps\web-cip && npm run build` |
| Build vendor UI | `cd apps\web-partners && npm run build` |
| Run tests | `python -m pytest tests/` |
