
#  Platform Contract

*(Integration Hub Platform)*

Version: 1.0
Scope: Backend Runtime, Admin UI, Vendor UI

This document defines the **core behavioral contract** for the platform.
It ensures that future changes, refactors, or AI-generated code **do not alter system guarantees**.

---

# 1. Platform Identity Model

## Vendor Identity

Vendor identity must always originate from the **authenticated JWT token**.

Canonical claim:

```json
bcpAuth
```

Example:

```json
{
  "sub": "user123",
  "bcpAuth": "LH001",
  "groups": ["integrationhub-vendors"]
}
```

### Rules

Vendor identity **must NOT come from:**

* request body
* query params
* headers
* UI selection
* cookies
* local storage

Vendor identity **must come from:**

```
JWT → bcpAuth claim
```

---

# 2. Backend Lambda Contract

All backend entrypoints must follow the same contract.

## Lambda Entry Points

Current runtime entrypoints:

```
routing_lambda.py
registry_lambda.py
vendor_registry_lambda.py
ai_gateway_lambda.py
audit_lambda.py
onboarding_lambda.py
endpoint_verifier_lambda.py
```

Each lambda must follow the lifecycle below.

---

# 3. Runtime Execution Contract

Applicable to:

```
routing_lambda
ai_gateway_lambda
```

### Required execution order

```
1. JWT validation
2. Vendor identity extraction
3. Policy evaluation
4. Feature gate validation
5. Allowlist verification
6. Request transformation
7. Downstream invocation
8. Audit logging
9. Canonical response
```

### Vendor identity rule

```python
vendor_code = jwt_claims["bcpAuth"]
```

Any mismatch between request and token must result in:

```
VENDOR_SPOOF_BLOCKED
```

---

# 4. Policy Engine Contract

Policy engine must be the **single centralized decision layer**.

Primary function:

```
evaluate_policy(context)
```

### Required checks

Policy engine must enforce:

```
AUTH_REQUIRED
AUTH_INVALID
ADMIN_GROUP_REQUIRED
VENDOR_CLAIM_MISSING
VENDOR_SPOOF_BLOCKED
ALLOWLIST_DENY
FEATURE_DISABLED
PHI_APPROVAL_REQUIRED
```

Policy decisions must be:

* deterministic
* explainable
* logged

---

# 5. Canonical Response Contract

All API responses must use canonical format.

Success:

```json
{
  "status": "SUCCESS",
  "data": {},
  "correlationId": "uuid"
}
```

Error:

```json
{
  "status": "ERROR",
  "code": "POLICY_DENIED",
  "message": "Allowlist restriction",
  "correlationId": "uuid"
}
```

### Forbidden patterns

Endpoints must NOT return:

```
{ "error": "something" }
{ "message": "failed" }
```

All errors must use canonical format.

---

# 6. Observability Contract

Every runtime action must emit metadata-only logs.

Audit events must never contain:

```
request_body
response_body
payload
PHI fields
```

Unless PHI access is explicitly expanded.

---

# 7. PHI Security Contract

PHI must be protected by default.

Default state:

```
PHI REDACTED
```

PHI expansion requires:

```
expandSensitive=true
+
PHI_APPROVED_GROUP
```

Expansion must generate audit events:

```
PHI_VIEW_ENABLED
PHI_VIEWED_TRANSACTION
```

---

# 8. Admin UI Contract

Admin UI represents the **platform control plane**.

Admin UI lives in:

```
apps/web-cip
```

---

## Admin Responsibilities

Admin UI provides:

* platform configuration
* vendor management
* policy governance
* runtime observability
* debugging tools
* AI tools

---

## Admin Feature Areas

### Home / Orientation

Platform overview and rollout phase guidance.

### Registry

Vendor and integration configuration.

Includes:

```
vendors
auth profiles
endpoints
contracts
access control
```

---

### Governance

Includes:

```
policy simulator
policy decision viewer
approvals
allowlist
```

---

### Observability

Includes:

```
transactions
audit
mission control
activity streams
```

---

### Optimization

Includes:

```
AI formatter
AI debugger
usage & billing
```

---

### Admin Restrictions

Admin UI must:

* require admin authentication
* enforce admin group membership
* respect PHI expansion gating
* treat debug tools as read-only unless explicitly designed otherwise

---

# 9. Vendor UI Contract

Vendor UI represents the **vendor experience plane**.

Vendor UI lives in:

```
apps/web-partners
```

---

## Vendor Responsibilities

Vendor UI allows vendors to:

* configure integrations
* build flows
* test integrations
* observe their transactions

---

## Vendor Feature Areas

### Home

Vendor onboarding and readiness guidance.

---

### Configuration

Vendor-managed settings:

```
auth profiles
endpoints
operation configuration
access visibility
```

Vendor must never edit platform-level configuration.

---

### Flow Builder

Allows vendor to map vendor payloads to canonical operations.

Builder must enforce:

```
schema validation
canonical structure
operation compatibility
```

---

### Execute / Sandbox

Vendor testing environment.

Must support:

```
vendor-scoped execution
safe testing
policy feedback
```

Must never allow:

```
cross-vendor execution
policy bypass
```

---

### Vendor Observability

Vendor may view:

```
their transactions
their execution results
their policy outcomes
```

Vendor must never view:

```
other vendor activity
platform-wide metrics
admin-only diagnostics
```

---

# 10. Route Ownership Contract

Routes define authority boundaries.

## Admin routes

```
/admin/*
```

Admin routes own:

```
registry
policy
approvals
mission control
audit
platform configuration
```

---

## Vendor routes

```
/home
/flows
/configuration
/execute
/transactions
```

Vendor routes own:

```
vendor configuration
vendor flows
vendor execution
vendor transaction history
```

---

## Forbidden combinations

Vendor UI must never expose:

```
platform registry
admin observability
cross-vendor configuration
```

Admin UI must never rely on vendor-only endpoints.

---

# 11. UI State Contract

UI must never be the source of truth for:

```
vendor identity
authorization
policy decisions
feature enablement
```

Those must come from backend.

UI may depend on:

```
JWT identity
feature flags
route params
backend responses
```

---

# 12. Rollout Phase Contract

Platform rollout occurs in phases.

Example phases:

```
Phase 0 — Minimum viable platform
Phase 1 — Build integrations
Phase 2 — Observe runtime
Phase 3 — Govern policies
Phase 4 — Optimize via AI
```

Phase flags control **visibility only**.

Security enforcement must remain active regardless of phase.

---

# 13. Platform Integrity Rules

The following must never be violated.

### Identity integrity

Vendor identity always comes from JWT.

### Security integrity

Policy engine must enforce access.

### Data integrity

Canonical schemas must validate integrations.

### UI integrity

Admin and Vendor UI must remain separated.

### Observability integrity

Logs must remain metadata-only unless PHI expansion approved.

---

# 14. Platform Validation Checklist

After any feature implementation verify:

### Backend

* JWT validation present
* vendor identity from JWT
* policy engine invoked
* canonical response used
* audit event emitted

---

### Admin UI

* admin authentication enforced
* PHI redaction respected
* routes protected
* governance tools functional

---

### Vendor UI

* vendor-scoped data only
* no cross-vendor exposure
* policy feedback visible
* sandbox execution safe

---

# 15. Future Modules (Conceptual)

Future product branding may organize platform modules as:

```
Syntegris Canon
Syntegris Flow
Syntegris Sandbox
Syntegris AI
Syntegris Policy
Syntegris Registry
Syntegris Runtime
Syntegris Mission Control
```

These names represent **conceptual modules** and do not require immediate code restructuring.

---

# 16. Contract Enforcement

This contract must be used to validate:

* new features
* refactors
* AI-generated code
* integration changes

Any deviation from this contract must be treated as a **platform regression**.

---

# Final Recommendation

Keep this document **short and stable** and use it as the **reference whenever Cursor writes new code**.

Then give Cursor instructions like:

> “Implement this feature but ensure it respects the Platform Contract.”

