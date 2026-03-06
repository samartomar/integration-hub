# Integration Hub – Architecture Document

## Overview 

Integration Hub is an AWS-based proof-of-concept for centralizing integration orchestration between licensees. It provides:

- **Control Plane**: Registry of licensees, operations, allowlists, and endpoints
- **Data Plane**: Execute integrations, audit transactions, and admin redrive
- **AI Assistant**: Amazon Bedrock Agent with ExecuteIntegration tool for conversational integration execution
- **CI/CD**: CodePipeline for build, migrate, and deploy

---

## High-Level Architecture

```
                                    ┌─────────────────────────────────────────────────────────────────┐
                                    │                         AWS Cloud                                 │
                                    │                                                                   │
  ┌──────────┐                      │   ┌──────────────────────────────────────────────────────────┐   │
  │ Postman  │─────── HTTPS ────────┼──▶│  API Gateway HTTP API (IntegrationHubApi)                  │   │
  │ / Client │                      │   │  https://xxx.execute-api.region.amazonaws.com              │   │
  └──────────┘                      │   └────────────────────────┬─────────────────────────────────┘   │
         │                          │                            │                                       │
         │                          │              ┌──────────────┴──────────────┐                      │
  ┌──────┴──────┐                   │              │                            │                      │
  │ Bedrock     │  invoke            │   ┌──────────▼──────────┐    ┌───────────▼──────────┐           │
  │ Agent       │───────────────────┼──▶│  AI Tool Lambda      │    │  Routing Lambda      │           │
  │ (Claude)    │                   │   │  (ExecuteIntegration)│    │  (orchestration)     │           │
  └─────────────┘                   │   └──────────┬───────────┘    └───────────┬──────────┘           │
                                    │              │                            │                      │
                                    │              └────────────┬───────────────┘                      │
                                    │                           │                                       │
                                    │              ┌────────────▼────────────┐                         │
                                    │              │  Registry Lambda        │                         │
                                    │              │  (Control Plane API)    │                         │
                                    │              └────────────┬────────────┘                         │
                                    │                           │                                       │
                                    │              ┌────────────▼────────────┐                         │
                                    │              │  Audit Lambda           │                         │
                                    │              │  (read transactions)    │                         │
                                    │              └────────────┬────────────┘                         │
                                    │                           │                                       │
                                    │   ┌──────────────────────┴──────────────────────┐               │
                                    │   │  VPC (Private Subnets)                        │               │
                                    │   │  ┌─────────────────────────────────────────┐  │               │
                                    │   │  │  Aurora PostgreSQL Serverless v2         │  │               │
                                    │   │  │  - control_plane schema                 │  │               │
                                    │   │  │  - data_plane schema                    │  │               │
                                    │   │  └─────────────────────────────────────────┘  │               │
                                    │   └──────────────────────────────────────────────┘               │
                                    │                                                                   │
                                    └─────────────────────────────────────────────────────────────────┘
```

---

## CDK Stacks (Deployment Order)

| Order | Stack | Purpose |
|-------|-------|---------|
| 1 | **FoundationStack** | VPC, security groups, IAM roles, EventBridge bus |
| 2 | **DatabaseStack** | Aurora PostgreSQL Serverless v2, schema creation |
| 3 | **OpsAccessStack** | SSM bastion, VPC endpoints (optional POC access) |
| 4 | **DataPlaneStack** | APIs, Lambdas, Bedrock Agent (Claude + ExecuteIntegration tool) |
| 5 | **PipelineStack** | CI/CD pipeline (GitHub → Build → Migrate) |

---

## Foundation Stack

| Resource | Description |
|----------|-------------|
| VPC | 2 AZs, public/private subnets |
| Lambda SG | Security group for Lambda functions |
| Aurora SG | Security group for Aurora |
| CodeBuild SG | For pipeline migrations (Aurora access) |
| Bastion SG | SSM-only bastion (POC ops) |
| IAM Roles | `integration_router_lambda_role`, `ai_tool_lambda_role`, `audit_lambda_role` |
| EventBridge | `integration-hub-events` bus |

---

## Database Stack

| Resource | Description |
|----------|-------------|
| Aurora Cluster | PostgreSQL 15.10, Serverless v2 (0.5–2 ACU) |
| Subnets | Private with egress only (no public internet) |
| Schema Init | Custom resource Lambda creates `control_plane`, `data_plane` schemas |
| Access | Lambda SG, Bastion SG, CodeBuild SG on 5432 |

**Schemas:**

- **control_plane**: vendors, operations, vendor_operation_allowlist, vendor_endpoints
- **data_plane**: transactions, audit_events

### Post-Baseline Schema Model

- **No HUB concept**: The system does not assume a special "hub" vendor. Wildcards use `is_any_source` / `is_any_target` booleans; no `*` literal or HUB vendor code.
- **Empty DB is first-class**: Fresh prod environments may have no data. All list endpoints return `200` with `items: []`; no 500s from missing tables or empty results.
- **Direction semantics**:
  - `operations.direction_policy`: `PROVIDER_RECEIVES_ONLY` \| `TWO_WAY`
  - `vendor_operation_allowlist.flow_direction`: `INBOUND` \| `OUTBOUND` \| `BOTH`
  - Vendor tables (`vendor_endpoints`, `vendor_supported_operations`, etc.): `flow_direction` is `INBOUND` \| `OUTBOUND` only (no `BOTH`)
- **Allowlist**: Admin rules (`rule_scope='admin'`) define allowed access; routing and vendor readiness derive from admin rules + vendor configuration.

---

## Data Plane Stack (Main API)

**Two APIs:**

1. **IntegrationHubVendorApi** (REST, API key for execute)
   - `POST /v1/integrations/execute` (apiKeyRequired=true) → Routing Lambda
   - `POST /v1/onboarding/register` (apiKeyRequired=false) → Onboarding Lambda

2. **IntegrationHubAdminApi** (HTTP API, no API key)
   - `POST /v1/admin/redrive/{transactionId}` → Routing Lambda
   - `GET /v1/audit/transactions` → Audit Lambda
   - `GET /v1/audit/transactions/{transactionId}` → Audit Lambda
   - `GET /v1/registry/contracts` → Registry Lambda
   - `GET /v1/registry/operations` → Registry Lambda
   - `POST /v1/registry/vendors` | `operations` | `allowlist` | `endpoints` → Registry Lambda

**Auth Flow (Vendor Execute – `POST /v1/integrations/execute`):**

The Hub supports two inbound auth modes for execute:

1. **JWT Bearer token** (Tier-3, IDP-issued): Validate via JWKS, extract vendor from claim, check vendor in DB.

**Precedence rules:**

- If `Authorization: Bearer <token>` present → **always try JWT**. 
- If `IDP_JWKS_URL` env var empty → JWT disabled; Bearer present returns `auth_error("JWT auth not configured")`.
- If no Bearer token.
- Body `sourceVendor` is always ignored; `AUTH_SOURCE_VENDOR_IGNORED` logged when present.

**Environment variables (JWT / Tier-3):**

| Variable        | Purpose                                |
|----------------|----------------------------------------|
| `IDP_JWKS_URL` | Required to enable JWT; empty = disabled |
| `IDP_ISSUER`   | Expected `iss` in JWT                  |
| `IDP_AUDIENCE` | Expected `aud` (comma-separated)       |
| `IDP_VENDOR_CLAIM` | Claim name for vendor_code (default: `vendor_code`) |
| `IDP_ALLOWED_ALGS` | Allowed algorithms (default: `RS256`)   |

**Example headers:**

- JWT: `Authorization: Bearer <JWT>`

- **CDK**: `IntegrationHubVendorApi` (REST), `POST /v1/integrations/execute` → `routing_lambda`
- **Lambda**: `apps/api/src/lambda/routing_lambda.py`
- **Order**: Auth → Parse body → Idempotency lookup → Validation → Allowlist (inside `validate_control_plane`) → Downstream call
- **Errors**: `auth_error()` → 401, `forbidden()` → 403, `vendor_not_found()` → 404
- **Audit**: `AUTH_JWT_SUCCEEDED`, `AUTH_JWT_FAILED`, `AUTH_SOURCE_VENDOR_IGNORED`

**Lambdas (all in VPC, private subnets):**

- **Routing Lambda**: Validates allowlist, calls downstream licensee, logs to `data_plane.transactions`
- **Audit Lambda**: Read-only queries with `vendorCode`, `limit`, `cursor`, `from`, `to`, `status`, `operation`
- **Registry Lambda**: Upserts control_plane tables (licensees, operations, allowlist, endpoints)
- **AI Tool Lambda**: Bedrock action-group; validates input, calls Integration Hub API, returns response

---

## Bedrock Agent Stack

| Resource | Description |
|----------|-------------|
| Agent | CentralIntegrationAgent (Claude 3 Sonnet) |
| Action Group | ExecuteIntegration → invokes AI Tool Lambda |
| Alias | `prod` for invocation |
| Instruction | From `packages/bedrock-assets/agent-system-prompt.txt` |
| Schema | From `packages/bedrock-assets/tool-schema.json` (sourceVendor, targetVendor, operationCode, canonicalVersion, parameters, idempotencyKey) |

---

## Ops Access Stack (POC)

| Resource | Description |
|----------|-------------|
| SSM Bastion | EC2 instance for port-forward to Aurora |
| VPC Endpoints | SSM, EC2 Messages, SSM Messages (no NAT for bastion) |
| Aurora Ingress | Bastion SG → Aurora on 5432 |

---

## CI/CD Pipeline

```
GitHub (main) → Source → Build → Migrate
```

### Source Stage

- CodeStar Connections to GitHub
- Branch: `main`

### Build Stage (CodeBuild, no VPC)

- **Install**: pip (requirements.txt, .[dev]), Node 20
- **Cache**: `/root/.cache/pip`, `/root/.npm`
- **Commands**: ruff, mypy, pytest
- **Pre-bundle**: Docker-based bundling of `apps/api/src/lambda` and `lambdas/ai_tool` → `.bundled/`
- **Artifacts**: Full source + `.bundled` passed to Migrate

### Migrate Stage (CodeBuild in VPC)

- **Input**: BuildOutput (includes `.bundled`)
- **Install**: pip, npm, aws-cdk
- **Cache**: Same as Build
- **Pre_build**: Resolve DB_SECRET_ARN, DB_HOST from CloudFormation
- **Build**: Alembic migrations, CDK deploy --all
- **Pre-bundle**: Fallback if `.bundled` missing (no Docker in VPC)

---

## Data Model

### control_plane

- **vendors**: vendor_code, vendor_name
- **operations**: operation_code, description, canonical_version, is_async_capable, is_active
- **vendor_operation_allowlist**: source_vendor_code, target_vendor_code, operation_code
- **vendor_endpoints**: vendor_code, operation_code, url, http_method, payload_format, timeout_ms, is_active

### data_plane

- **transactions**: transaction_id, correlation_id, source_vendor, target_vendor, operation, idempotency_key, status, created_at
- **audit_events**: transaction_id, action, vendor_code, details (JSONB)

---

## Security

- Aurora: private subnets only, no public access
- Lambdas: VPC-attached, private subnets, Secrets Manager for DB creds
- API Gateway: public endpoint; auth/API key can be added
- Bedrock: IAM role allows invoke of AI Tool Lambda only

---

## Key Files

| Path | Purpose |
|------|---------|
| `app.py` | CDK app entry, stack ordering |
| `infra/stacks/*.py` | CDK stack definitions |
| `apps/api/src/lambda/` | routing_lambda, audit_lambda, registry_lambda |
| `lambdas/ai_tool/` | AI Tool Lambda (Bedrock action) |
| `lambdas/router/` | Alternate router (RoutingLambdaStack) |
| `lambdas/schema_init/` | Schema creation Lambda |
| `apps/api/migrations/` | Alembic migrations |
| `packages/bedrock-assets/` | Agent prompt, tool schema |
| `tooling/scripts/` | run-migrations, run-ssm-port-forward, seed_control_plane |
| `tooling/pipelines/buildspec-*.yml` | Pipeline build specs |

---

## Local Development

1. **SSM port-forward**: `.\tooling\scripts\run-ssm-port-forward.ps1` (requires OpsAccessStack)
2. **Migrations**: `.\tooling\scripts\run-migrations.ps1` or `python tooling/scripts/run_migrations.py`
3. **Seed**: `psql $DATABASE_URL -f tooling/scripts/seed_control_plane.sql`
4. **Provider endpoint (LH002)**: configured via seeded endpoint URL in local/dev
