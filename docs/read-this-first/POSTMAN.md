# Postman – Integration Hub POC

Single collection and environment for all Integration Hub API endpoints.

**The `postman/` folder is gitignored.** Generate it before first use:

```powershell
python tooling/scripts/generate_postman.py
```

This creates `postman/` with the collection and environment files.

---

## Files (after generation)

| File | Purpose |
|------|---------|
| `postman/Integration-Hub-POC.postman_collection.json` | Collection with all endpoints |
| `postman/Integration-Hub-POC.postman_environment.json` | Environment variables (AWS) |
| `postman/Integration-Hub-POC-Local.postman_environment.json` | Local dev (localhost:8080, JWT) |

## Regenerate

When new endpoints are added, run:

```powershell
python tooling/scripts/generate_postman.py
```

---

## Import

1. **Collection:** Import → `postman/Integration-Hub-POC.postman_collection.json`
2. **Environment:** Import → `postman/Integration-Hub-POC.postman_environment.json` (AWS) and/or `postman/Integration-Hub-POC-Local.postman_environment.json` (local)
3. Select the environment before running requests

For **local development** (`make local-up`): use the **Integration Hub - Local** environment. All URLs = `http://localhost:8080`, keys = `local-dev` / `local-admin`.

---

## Get API URLs and Keys (Auto-Wired)

After deploying **DataPlaneStack**:

```powershell
.\tooling\scripts\get-postman-urls.ps1 -Update
```

This fetches Vendor, Admin, and Runtime API URLs from CloudFormation outputs and updates `postman/Integration-Hub-POC.postman_environment.json`. When custom domains are configured (`AdminApiCustomDomainUrl`, `RuntimeApiCustomDomainUrl`), the script prefers those over AWS invoke URLs.

**API keys** (obtain from deploy or pipeline, not console):

- **vendorJwt** — Vendor JWT for /v1/integrations/execute (Authorization: Bearer).
- **adminJwt** — Admin JWT for registry, audit, redrive (Authorization: Bearer).
- **runtimeJwt** — Runtime JWT for /v1/execute, /v1/ai/execute (Authorization: Bearer).

---

## Endpoints (folders)

- **Runtime API** — POST /v1/execute, POST /v1/ai/execute (JWT: Authorization Bearer)
- **Integrations** — Execute (POST /v1/integrations/execute) — vendor portal
- **AI Endpoint** — AI Execute DATA/PROMPT (POST /v1/ai/execute) — admin/legacy
- **Onboarding** — Register Vendor (POST /v1/onboarding/register)
- **Admin** — Redrive (POST /v1/admin/redrive/{id})
- **Audit** — List Transactions, Get by ID, Get Events
- **Registry (Admin)** — Contracts, Vendors, Operations, Allowlist, Change Requests, Endpoints, Auth Profiles, Readiness
- **Vendor Registry** — Config bundle, API keys, Supported ops, Endpoints, Contracts, Canonical, Auth, Allowlist, Change requests, Transactions, Operations, Mappings, Flows
