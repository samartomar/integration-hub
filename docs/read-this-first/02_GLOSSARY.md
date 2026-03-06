# Glossary

Terms used across the Integration Hub codebase and docs.

---

## A

**Admin** – Platform owner or governance role. Defines canonical models, approves/rejects change requests, configures allowlist and global standards.

**Allowlist** – Rules defining *who may call whom* for which operation. Format: `(source_vendor, target_vendor, operation)`. Wildcards allowed (`source=*`, `target=*`). Nothing works until an admin allows it.

**Aurora** – AWS Aurora PostgreSQL (Serverless v2) used for `control_plane` and `data_plane` schemas.

---

## C

**Canonical** – The standard, hub-defined format for an operation. Canonical contracts and mappings are the default; vendors can override per direction.

**Canonical pass-through** – When no vendor mapping exists and the payload fits the canonical schema, the Hub passes it through without transformation. Show "Using canonical format" in the UI, not "Missing mapping."

**Change request** – Vendor-submitted request to modify allowlist, endpoint, mapping, or contract. Admin approves or rejects.

**Control plane** – DB schema and APIs for configuration: vendors, operations, allowlist, endpoints, contracts, mappings, change requests.

**Contract** – Expected shape of request and response (schema). One canonical per operation; vendors can provide overrides per direction (OUTBOUND/INBOUND).

---

## D

**Data plane** – DB schema and logic for execution: transactions, audit events, metrics.

**Direction** – Flow direction of a call:
- **OUTBOUND**: vendor (caller) → external (provider)
- **INBOUND**: external (caller) → vendor (provider)
- **BOTH**: used in allowlist rules for two-way flows

---

## E

**Effective contract** – The contract actually used for validation. Vendor override wins per direction; if none, canonical is used. Use `load_effective_contract(flow_direction)` everywhere.

**Effective endpoint** – The endpoint used for a given (operation, vendor, flow_direction). Resolved via `load_effective_endpoint(...)`; only active endpoints considered.

**Effective mapping** – The mapping used for transformation. Vendor mapping overrides canonical pass-through. Resolved via `resolve_effective_mapping(flow_direction)`.

**Endpoint** – Where the Hub sends the actual HTTP request for a vendor/operation. URL, method, timeout; must be active (`is_active=true`).

**Execute** – The main runtime flow: validate request → check allowlist → load contract/mapping/endpoint → call downstream → return canonical response.

---

## F

**Feature gate** – Controls whether vendor edits are direct-write or require admin approval. Examples: `mapping_edit`, `contract_edit`, `endpoint_edit`, `allowlist_edit`.

**Flow direction** – See **Direction**.

---

## I

**INBOUND** – Flow where external system calls the vendor. In allowlist, vendor is the **target**.

**Idempotency key** – Optional key on execute requests to prevent duplicate processing of the same logical operation.

**Include actuals** – When `includeActuals=true`, the response includes actual request/response payloads for debugging. Invariant: always included when requested.

**Integration Hub** – Central broker for multi-vendor integrations. Validates, governs, transforms, routes.

---

## J

**JWT** – JSON Web Token from Auth0. The **only** source of vendor identity. Never read vendor from headers or body. Vendor code from a single claim (e.g. `vendor_code`).

---

## M

**Mapping** – Translation rules between canonical format and vendor format. Request mapping (canonical → vendor) and response mapping (vendor → canonical).

**My-allowlist** – Vendor-facing view of allowlist:
- **OUTBOUND**: vendor is source (who can I call?)
- **INBOUND**: vendor is target (who can call me?)

---

## O

**Operation** – A type of action (e.g. GET_RECEIPT, GET_WEATHER). Has canonical contract; vendors can override.

**OUTBOUND** – Flow where vendor calls external system. In allowlist, vendor is the **source**.

---

## P

**Portal** – Web UI. Admin portal for governance; Vendor portal for self-service.

**Provider** – Vendor receiving a request (inbound side). Opposite of caller.

---

## R

**Runtime API** – Headless API for machines: `POST /v1/execute` and `POST /v1/ai/execute` with JWT (Authorization: Bearer). Used by external systems, M2M, AI.

**Runtime caller** – System or app that sends canonical requests and receives canonical responses. Does not need vendor-specific knowledge.

---

## S

**Source vendor** – Vendor initiating the call (outbound side).

**Target vendor** – Vendor receiving the call (inbound side).

---

## V

**Vendor** – Partner or system participating in the Hub (e.g. LH001, LH002). Can be caller (source) or provider (target).

**Vendor plane** – Vendor portal + vendor APIs (`/v1/vendor/*`).

---

## Error Codes (Common)

| Code | Meaning |
|------|---------|
| `ACCESS_DENIED` | Outbound blocked by allowlist |
| `CONTRACT_NOT_FOUND` | Neither vendor nor canonical contract exists |
| `ENDPOINT_NOT_FOUND` | No active endpoint for (vendor, operation, direction) |
| `MAPPING_NOT_FOUND` | Mapping required (e.g. vendor contract override) but missing |

---

Next: [03_ARCHITECTURE.md](03_ARCHITECTURE.md)
