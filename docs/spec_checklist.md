
## 1. Authentication & Tenant Isolation

### JWT + Identity

[ ] JWT signature MUST be validated for every request.
* [ ] Invalid JWT MUST return **401 UNAUTHORIZED**.
* [ ] Valid JWT MUST produce exactly one of:

* [ ] `vendor_code` (vendor)
* [ ] `admin` role (admin)
* [ ] runtime principal (runtime-only APIs)
* [ ] Vendor APIs MUST reject admin-scoped tokens.
* [ ] Admin APIs MUST reject vendor-scoped tokens.
* [ ] Runtime APIs MUST NOT treat tokens as vendor identity.
* [ ] Vendor-facing APIs MUST fail with **403** when no vendor identity is derivable.
* [ ] All vendor DB queries MUST filter by `vendor_code`.
* [ ] Vendor A MUST NOT see or modify vendor B records.

---

## 2. Contracts (Canonical + Vendor Override)

### Effective Contract Rule

* [ ] Canonical contract MUST exist for each `(operation, version, direction)` used in routing.
* [ ] Vendor override MUST take precedence if present.
* [ ] Canonical contract MUST be fallback when vendor override absent.
* [ ] Missing both canonical + vendor contract MUST return:

  * [ ] `CONTRACT_NOT_FOUND`
  * [ ] `category=NOT_FOUND`

### Contract Validation

* [ ] Incoming canonical request MUST validate against effective request schema.
* [ ] Vendor → canonical response MUST validate against effective response schema.
* [ ] Validation failure MUST produce:

  * [ ] `SCHEMA_VALIDATION_FAILED`
  * [ ] `category=VALIDATION`
  * [ ] `details.stage` set correctly.

---

## 3. Mappings (Request/Response)

### Resolution

* [ ] Vendor mappings MUST override canonical pass-through.
* [ ] When no vendor mappings exist:

  * [ ] Canonical pass-through MUST be used.
  * [ ] MUST NOT error solely due to “mapping missing.”

### Failures

* [ ] Mapping failures MUST produce:

  * [ ] `MAPPING_FAILED`
  * [ ] `details.stage = REQUEST_MAPPING` or `RESPONSE_MAPPING`
* [ ] Mapping failures MUST NOT reach vendor endpoint.

---

## 4. Allowlist (Access Control)

### Rules

* [ ] `(source=V1, target=V2, op)` MUST allow V1 → V2 calls.
* [ ] `source=*` MUST mean “any vendor may call the target”.
* [ ] `target=*` MUST mean “vendor may call any target”.

### Decision Logic

* [ ] Allowlist MUST be checked before routing.
* [ ] Allowed rules MUST permit runtime execution.
* [ ] Missing rule MUST produce:

  * [ ] `ACCESS_DENIED`
  * [ ] `category=AUTHORIZATION`

---

## 5. Endpoints (Vendor HTTP Destinations)

### Resolution

* [ ] Endpoint lookup MUST match `(vendor, operation, direction)`.
* [ ] Precedence MUST be:

  * [ ] (1) exact match
  * [ ] (2) fallback_any (wildcards)
* [ ] Endpoint metadata MUST annotate the source (exact/fallback).

### Failures

* [ ] Missing active endpoint MUST return:

  * [ ] `ENDPOINT_NOT_FOUND`
  * [ ] `category=NOT_FOUND`
* [ ] Inactive/disabled endpoints MUST NOT be used.

---

## 6. Runtime Execute (End-to-End Flow)

### Core Steps

For every runtime request, system MUST execute in this order:

* [ ] 1. Authenticate JWT
* [ ] 2. Derive source vendor
* [ ] 3. Load effective contract
* [ ] 4. Validate canonical request
* [ ] 5. Check allowlist
* [ ] 6. Resolve mappings
* [ ] 7. Resolve endpoint
* [ ] 8. Call vendor endpoint
* [ ] 9. Map vendor ↓ canonical
* [ ] 10. Validate canonical response
* [ ] 11. Write audit + transaction record
* [ ] 12. Return canonical response

### Error Handling

* [ ] Validation → `VALIDATION`
* [ ] Missing contract/endpoint → `NOT_FOUND`
* [ ] Downstream vendor HTTP error → `DOWNSTREAM`
* [ ] Unexpected exception → `INTERNAL`

### Actuals

When `includeActuals=true`:

* [ ] MUST return mapping + contract + endpoint sources.
* [ ] MUST include canonical/vendor request/response snapshots.
  When false:
* [ ] MUST NOT include actuals block.

---

## 7. AI Gateway

### DATA Requests

* [ ] Requires `operationCode`, `targetVendorCode`, `payload`.
* [ ] MUST execute via routing + return canonical response.
* [ ] Formatter MUST follow op-level + request-level rules.
* [ ] RAW_ONLY MUST suppress formatter.

### PROMPT Requests

* [ ] MUST call Bedrock Agent.
* [ ] MUST return `finalText` from agent.
* [ ] MUST NOT apply formatter.

### Errors

* [ ] Bedrock errors MUST return `AGENT_INVOKE_ERROR` without breaking runtime success.

---

## 8. Feature Gates

* [ ] MUST load gate state from DB.
* [ ] When disabled, MUST default to old baseline behavior.
* [ ] Gate failures MUST degrade gracefully (fail-safe).

---

## 9. Portals (Vendor/Admin)

### Vendor Portal

* [ ] MUST only call vendor API.
* [ ] MUST reload config bundle on vendor switch/login.
* [ ] MUST reflect backend state (no stale local caches).
* [ ] MUST hide admin-only fields.

### Admin Portal

* [ ] MUST only accept admin JWTs.
* [ ] MUST persist changes through proper admin flows.
* [ ] MUST not expose vendor-only features.

---

## 10. Local Dev & Environment Behavior

* [ ] Local dev MUST run via docker-compose or make targets.
* [ ] Alembic MUST be the only source of schema creation.
* [ ] Seed MUST be idempotent.
* [ ] Local portals MUST target local API endpoints (env-driven).
* [ ] No AWS calls when in local mode.
