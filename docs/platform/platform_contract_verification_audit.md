Perform a full platform verification against the Platform Contract.

Goal:
Verify that the implementation across backend lambdas and UI follows the defined Platform Contract.

Scope:
apps/api/src/lambda
apps/web-cip
apps/web-partners

PART 1 — Lambda entrypoint verification

List all lambda entrypoints:

routing_lambda
registry_lambda
vendor_registry_lambda
ai_gateway_lambda
audit_lambda
onboarding_lambda
endpoint_verifier_lambda

For each lambda verify:

1. JWT validation present
2. vendor identity extracted only from JWT claim bcpAuth
3. evaluate_policy() called before business logic
4. canonical_response or canonical_error used
5. audit events emitted where required
6. no request-body vendor override allowed

Produce table:

Lambda | Identity Source | Policy Enforced | Canonical Response | Audit | Issues

---

PART 2 — Security contract verification

Check for violations:

vendor identity read from body/header
missing policy engine call
missing admin_guard for admin routes
PHI expansion without approval group
non-canonical error responses

List any violations.

---

PART 3 — UI contract verification

Admin UI (apps/web-cip)

Verify:

admin routes protected
PHI expansion gated
admin-only tools not exposed to vendors
UI not acting as source of truth for identity

Vendor UI (apps/web-partners)

Verify:

vendor identity comes from backend
no cross-vendor visibility
execute scoped to vendor
no admin features exposed

Produce table:

UI Area | Contract Requirement | Status | Issues

---

PART 4 — Policy engine coverage

Verify evaluate_policy() is used in:

routing_lambda
vendor_registry_lambda
registry_lambda
audit_lambda
ai_gateway_lambda

List any missing coverage.

---

PART 5 — Feature drift detection

Detect duplicated identity logic in:

jwt_auth
jwt_authorizer
bcp_auth
vendor_identity
vendor_auth_resolver

Identify which implementation is actually used.

---

PART 6 — Final report

Produce:

1. Contract compliance score
2. List of violations
3. Missing implementations
4. Recommended fixes
5. Risk severity (HIGH / MEDIUM / LOW)