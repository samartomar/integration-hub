# Feature Production Readiness

## Scope

Current production-maturity scope for the Integration Hub integration adoption feature set.

### Supported Operations

- GET_VERIFY_MEMBER_ELIGIBILITY
- GET_MEMBER_ACCUMULATORS

### Supported Vendor Pair

- LH001 → LH002 (source → target)

### Surfaces

- **Admin:** Adoption Workbench, Canonical Explorer, Flow Builder, Sandbox, AI Debugger, Runtime Preflight, Canonical Execute, Mission Control, Mapping Readiness / Onboarding / Release Bundle
- **Partner:** Partner Canonical Explorer, Flow Builder, Sandbox, AI Debugger, Runtime Preflight, Canonical Execute (vendor-scoped)

**Note:** Internal identifiers (e.g. API paths `/v1/syntegris/*`, component names) may retain legacy naming for compatibility. User-facing labels use neutral terms.

For the cutover model (canonical-first as primary path for the supported slice), see [Canonical-First Cutover Model](../product/canonical_first_cutover_model.md).

## Required Configs / Flags

| Config | Purpose |
|--------|---------|
| IDP_ISSUER | JWT validation |
| AI_GATEWAY_FUNCTION_ARN | AI formatter/debugger invoke |
| BEDROCK_DEBUGGER_ENABLED | Enable debugger enrichment |
| BEDROCK_DEBUGGER_MODEL_ID | Bedrock model for debugger |
| RUNTIME_API_URL | Canonical bridge execute |
| DB_URL or DB_SECRET_ARN | Registry persistence |

## E2E Operator Flow

1. Adoption Workbench → see inventory and adoption status, deep-link to next action
2. Canonical Explorer → browse operations
3. Flow Builder → design flow, generate handoff
4. Sandbox → validate requests
4. AI Debugger → debug with enhancement
5. Runtime Preflight → validate envelope
6. Canonical Execute → run (DRY_RUN or EXECUTE)
7. Mission Control → observe transactions
8. Mapping Readiness → release bundle, verification checklist

## Known Intentional Non-Goals

- No automatic apply of mapping changes
- No cross-vendor data visibility
- No bulk ETL or batch pipelines
