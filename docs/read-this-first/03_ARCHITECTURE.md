# Architecture

High-level architecture of the Integration Hub. See `docs/ARCHITECTURE.md` for more detail.

---

## Four Planes

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Integration Hub                               │
│                                                                       │
│  Control Plane          Vendor Plane         Runtime Plane   AI       │
│  (Admin Registry)       (Portal + API)       (Execute)      Gateway  │
│  - vendors              - /v1/vendor/*       - /v1/execute   - PROMPT │
│  - operations           - self-service       - /v1/ai/*      - DATA   │
│  - allowlist            - change requests                             │
│  - endpoints, mappings, contracts                                    │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │  Aurora PostgreSQL (control_plane + data_plane)                   ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

---

## APIs

| API | Auth | Paths | Use |
|-----|------|-------|-----|
| **Vendor API** | JWT | `/v1/vendor/*`, `/v1/integrations/execute` | Vendor portal, partners |
| **Admin API** | JWT (Authorization: Bearer) | `/v1/registry/*`, `/v1/audit/*`, `/v1/admin/redrive` | Admin portal, internal tooling |
| **Runtime API** | JWT (Authorization: Bearer) | `/v1/execute`, `/v1/ai/execute` | Headless, M2M, external systems |
| **Health** | — | `/health` | Liveness check |

---

## CDK Stacks (Deployment Order)

| Order | Stack | Purpose |
|-------|-------|---------|
| 1 | **FoundationStack** | VPC, security groups, IAM roles, EventBridge |
| 2 | **DatabaseStack** | Aurora PostgreSQL, schema init (control_plane, data_plane) |
| 3 | **OpsAccessStack** | SSM bastion, VPC endpoints (ops access) |
| 4 | **DataPlaneStack** | APIs, Lambdas, Bedrock Agent |
| 5 | **PipelineStack** | CI/CD (GitHub → Build → Migrate → Deploy) |
| — | **PortalStack** | S3 + CloudFront for Admin and Vendor UIs |
| — | **ProdPipelineStack** | Prod pipeline (cross-account deploy) |

---

## Lambdas

| Lambda | Location | Responsibility |
|--------|----------|-----------------|
| **routing_lambda** | `apps/api/src/lambda/routing_lambda.py` | Execute: validate, allowlist, contract, mapping, endpoint, downstream call, record tx |
| **vendor_registry_lambda** | `apps/api/src/lambda/vendor_registry_lambda.py` | Vendor CRUD: endpoints, mappings, contracts, allowlist view, change requests |
| **registry_lambda** | `apps/api/src/lambda/registry_lambda.py` | Admin CRUD: vendors, operations, allowlist, endpoints, contracts, mappings, approve/reject |
| **audit_lambda** | `apps/api/src/lambda/audit_lambda.py` | Read transactions and audit events |
| **ai_gateway_lambda** | `apps/api/src/lambda/ai_gateway_lambda.py` | AI execute: PROMPT (Bedrock Agent) or DATA (execute + formatter) |
| **onboarding_lambda** | `apps/api/src/lambda/onboarding_lambda.py` | Vendor self-registration, API key issuance |
| **endpoint_verifier_lambda** | `apps/api/src/lambda/endpoint_verifier_lambda.py` | EventBridge `endpoint.upserted` → validate endpoint |

---

## Database Schemas

### control_plane

- **vendors** – vendor_code, vendor_name, is_active
- **operations** – operation_code, description, canonical_version, direction_policy
- **vendor_operation_allowlist** – source, target, operation, flow_direction
- **vendor_endpoints** – vendor_code, operation_code, url, http_method, flow_direction, is_active
- **vendor_operation_contracts** – vendor/operation/direction overrides
- **vendor_operation_mappings** – request/response mapping templates
- **vendor_change_requests** – PENDING/APPROVED/REJECTED/CANCELLED

### data_plane

- **transactions** – transaction_id, source_vendor, target_vendor, operation, status, created_at
- **audit_events** – transaction_id, action, vendor_code, details (JSONB)

---

## AI Gateway Modes

| Mode | Behavior |
|------|----------|
| **PROMPT** | Bedrock Agent (Claude) + AI Tool Lambda → Hub API. Conversational. |
| **DATA** | Calls Runtime `/v1/execute` + optional Bedrock formatter (InvokeModel). |

IAM: must grant `bedrock:InvokeAgent` on **agent-alias**, not agent.

---

## Local vs AWS

| Layer | Local | AWS |
|-------|-------|-----|
| DB | Docker Postgres | Aurora Serverless v2 |
| API | Uvicorn (`apps/api/local/app.py`) | API Gateway + Lambda |
| Auth | Auth0 dev tenant or local JWT | Auth0 (issuer, audience, JWKS) |
| Provider endpoint | Configured endpoint URL | Real vendors or demo endpoint |

---

Next: [04_KEY_CONCEPTS.md](04_KEY_CONCEPTS.md)
