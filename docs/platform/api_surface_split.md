# API Surface Split

This document describes the split between Admin and Partner API surfaces, shared service layer, and vendor identity derivation rules.

---

## 1. Shared Service Layer

The Integration Hub uses a **single shared domain/service implementation** for Syntegris product features:

- **Canonical Explorer** – `schema.canonical_registry` (list_operations, get_operation)
- **Sandbox** – `schema.sandbox_runner` (validate_sandbox_request, run_mock_sandbox_test)
- **AI Debugger** – `ai.integration_debugger` (analyze_canonical_request, analyze_flow_draft, analyze_sandbox_result)
- **Runtime Preflight** – `schema.canonical_runtime_preflight` (run_canonical_preflight)
- **Canonical Execute / Bridge** – `schema.canonical_runtime_bridge` (run_canonical_bridge)

A thin transport layer (`apps/api/src/shared/syntegris_feature_handlers.py`) wraps these services for use by both admin and partner endpoints. It contains no auth assumptions; the caller injects vendor identity and enforces scoping.

---

## 2. Admin API Surface

**Gateway:** Admin API Gateway  
**Audience:** `ADMIN_API_AUDIENCE`  
**Lambda:** `registry_lambda`

### Responsibilities

- Cross-vendor operations
- Control-plane registry (vendors, operations, allowlist, endpoints, contracts)
- Canonical Explorer (schema-backed)
- Sandbox (validate, mock run)
- AI Debugger (request, flow-draft, sandbox-result analyze)
- Runtime Preflight
- Canonical Execute / Bridge
- Mission Control (observability, metadata-only)
- Change requests and approvals

### Routes (examples)

- `/v1/registry/*` – control-plane CRUD
- `/v1/flow/*` – flow drafts
- `/v1/sandbox/*` – sandbox validate, mock run
- `/v1/ai/debug/*` – AI debugger
- `/v1/runtime/canonical/preflight`
- `/v1/runtime/canonical/execute`

Admin endpoints may accept `sourceVendor` in the request body for cross-vendor scenarios.

---

## 3. Partner API Surface

**Gateway:** Vendor API Gateway  
**Audience:** `VENDOR_API_AUDIENCE`  
**Lambda:** `vendor_registry_lambda`

### Responsibilities

- Vendor-scoped operations only
- No cross-vendor behavior
- Same Syntegris features as admin, but with `sourceVendor` derived from JWT
- Canonical Explorer (schema-backed)
- Sandbox (validate, mock run)
- AI Debugger
- Runtime Preflight
- Canonical Execute / Bridge

### Routes (under `/v1/vendor/syntegris/`)

| Feature           | Method | Path                                                   |
|------------------|--------|--------------------------------------------------------|
| Canonical Explorer | GET    | `/v1/vendor/syntegris/canonical/operations`            |
| Canonical Explorer | GET    | `/v1/vendor/syntegris/canonical/operations/{opCode}`  |
| Sandbox           | POST   | `/v1/vendor/syntegris/sandbox/request/validate`      |
| Sandbox           | POST   | `/v1/vendor/syntegris/sandbox/mock/run`               |
| AI Debugger       | POST   | `/v1/vendor/syntegris/ai/debug/request/analyze`       |
| AI Debugger       | POST   | `/v1/vendor/syntegris/ai/debug/flow-draft/analyze`    |
| AI Debugger       | POST   | `/v1/vendor/syntegris/ai/debug/sandbox-result/analyze`|
| Runtime Preflight | POST   | `/v1/vendor/syntegris/runtime/canonical/preflight`    |
| Canonical Execute | POST   | `/v1/vendor/syntegris/runtime/canonical/execute`      |

Mission Control and admin-only observability endpoints are **not** exposed on the partner API.

---

## 4. Vendor Identity Derivation Rules

### Rule: sourceVendor from JWT only

For partner endpoints, `sourceVendor` must be derived **only** from the authenticated JWT:

- Claim: `bcpAuth` (via `_resolve_vendor_code_from_jwt`)
- **Never** from request body, query params, headers, or UI state

### Rule: Reject spoofed sourceVendor

If the request body includes `sourceVendor` (or `source_vendor`) and it **does not match** the authenticated vendor identity:

- Return **403 FORBIDDEN**
- Error code: `VENDOR_SPOOF_BLOCKED`
- Message: "Request sourceVendor does not match authenticated vendor identity"

Partner handlers call `_reject_source_vendor_spoof(body, auth_vendor)` before processing. No silent overwrite when mismatch is explicit; reject consistently.

### Rule: Overwrite for processing

When no spoof is detected, partner handlers overwrite `sourceVendor` in the payload with the auth-derived value before calling the shared service. This ensures the downstream logic always uses the correct vendor.

---

## 5. Why sourceVendor Must Come from Auth

1. **Security:** A partner must not act on behalf of another vendor.
2. **Audit:** All actions are attributed to the authenticated vendor.
3. **Policy:** Allowlist and access checks use the real caller identity.
4. **Platform contract:** The platform contract requires vendor identity from JWT only.

---

## 6. Why Explicit Mismatch Returns VENDOR_SPOOF_BLOCKED

When the body contains `sourceVendor` that differs from the JWT:

- **Reject** (do not silently overwrite) to make spoofing attempts explicit and auditable.
- Return a canonical error with code `VENDOR_SPOOF_BLOCKED` so clients and monitoring can detect and respond to spoof attempts.

---

## 7. Gateway Boundaries

- **Admin API Gateway** – `/v1/registry/*`, `/v1/flow/*`, `/v1/sandbox/*`, `/v1/ai/debug/*`, `/v1/runtime/canonical/*`
- **Vendor API Gateway** – `/v1/vendor/*` (including `/v1/vendor/syntegris/*`)

No gateway may proxy or borrow endpoints from another boundary.

---

## 8. Vendor Routes Must Remain Vendor-Scoped

Partner routes must not:

- Expose cross-vendor behavior
- Depend on admin-only APIs unless explicitly proxied and permission-safe
- Require admin group membership

Vendor routes evaluate centralized policy (`evaluate_policy` with `surface="VENDOR"`) before business logic.
