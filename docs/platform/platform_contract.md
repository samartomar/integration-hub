# Platform Contract
Version: 1.0

This document defines the required behavior of the platform across backend and UI.
It is the source of truth for future implementation, review, and regression checks.

---

## 1. Identity Contract

### Vendor identity
Vendor identity must come only from the authenticated JWT claim:

- `bcpAuth`

Vendor identity must **not** come from:

- request body
- query parameters
- headers
- UI state
- local storage

If a request contains a vendor identifier that does not match the authenticated JWT vendor, the request must be denied with:

- `VENDOR_SPOOF_BLOCKED`

### Admin identity
Admin capabilities must require:

- valid admin JWT
- required admin group membership

---

## 2. Backend Lambda Contract

All new protected HTTP lambdas should use the shared lambda entry contract (`apps/api/src/shared/lambda_entry_contract.py`) unless there is a documented reason not to.

All HTTP lambda entrypoints must follow this order:

1. Authenticate request
2. Resolve identity from JWT
3. Evaluate policy
4. Validate feature/route access
5. Execute business logic
6. Return canonical response
7. Emit audit/observability metadata where required

Required entrypoints include:

- `routing_lambda.py`
- `registry_lambda.py`
- `vendor_registry_lambda.py`
- `ai_gateway_lambda.py`
- `audit_lambda.py`
- `onboarding_lambda.py`

Worker lambdas (for example EventBridge/background processors) are exempt from JWT identity requirements but must still follow safe response/logging behavior.

---

## 3. Policy Contract

Protected lambdas must call centralized policy evaluation before business logic.

Primary entrypoint:

- `evaluate_policy(...)`

Policy evaluation must enforce, where applicable:

- auth required
- valid identity
- admin group checks
- vendor spoof prevention
- allowlist enforcement
- feature gating
- PHI gating

---

## 4. Canonical Response Contract

Protected APIs must return canonical success/error envelopes.

### Success
Responses should use platform-standard success helpers.

### Error
Responses should use platform-standard error helpers.

Protected routes must not return ad hoc error objects such as:

- `{ "error": ... }`
- `{ "message": ... }`

### Allowed exception
If a subsystem intentionally uses a custom response envelope, it must be documented explicitly.
Example:
- `ai_gateway_lambda.py` may use an AI-specific envelope if that behavior is intentional and stable.

---

## 5. PHI / Privacy Contract

Sensitive data must be redacted by default.

PHI expansion requires:

- explicit request (`expandSensitive=true`)
- approved group membership
- audit trail

Mission Control, policy decision logs, and observability endpoints must return **metadata only** and must never expose:

- request body
- response body
- debug payload
- PHI/PII fields

---

## 6. Admin UI Contract

Admin UI is the control and observability plane.

Admin UI may expose:

- registry/configuration
- policy tools
- approvals
- audit/transactions
- mission control
- AI/admin tools

Admin UI must:

- require admin auth
- respect PHI gating
- never use UI state as the source of truth for identity or authorization

---

## 7. Vendor UI Contract

Vendor UI is the vendor-scoped experience plane.

Vendor UI may expose only:

- vendor-scoped configuration
- vendor-scoped flows
- vendor-scoped execute/sandbox
- vendor-scoped transactions/diagnostics

Vendor UI must never expose:

- admin-only controls
- cross-vendor data
- platform-wide internal governance views

Vendor identity must always be backend-derived from JWT, not selected by the UI in production.

---

## 8. Route Ownership Contract

### Admin routes own:
- platform-wide configuration
- governance
- policy
- mission control
- audit/transactions
- approvals

### Vendor routes own:
- vendor configuration
- vendor flows
- vendor execution
- vendor-scoped transaction history
- vendor diagnostics

Admin behavior must not leak into vendor routes.
Vendor routes must not depend on admin-only APIs unless explicitly proxied and permission-safe.

---

## 9. Rollout / Feature Contract

Feature flags and phases control **visibility**, not security truth.

Rules:

- missing flag => disabled
- disabled routes must fail safely
- feature hiding must not relax backend enforcement
- backend security remains active regardless of rollout phase

---

## 10. Platform Integrity Rules

These must always remain true:

- vendor identity comes from JWT `bcpAuth`
- protected lambdas call policy evaluation
- protected APIs use canonical responses (except documented exceptions)
- PHI is redacted by default
- admin and vendor boundaries remain separate
- vendor spoofing is blocked

Any violation of these rules is a platform regression.

---

## 11. Lambda Entry Contract

All new protected HTTP lambdas should use the shared lambda entry contract (`apps/api/src/shared/lambda_entry_contract.py`) unless there is a documented reason not to.