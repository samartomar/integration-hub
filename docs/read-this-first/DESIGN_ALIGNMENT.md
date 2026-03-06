# Design Alignment: DB ↔ Backend ↔ Semantics

This document records the resolution of system-level design issues and the current alignment between DB schema, backend behavior, and platform semantics.

---

## 1. Endpoint Uniqueness Model ✅

**Design expectation:** Each vendor+operation+direction has **only one active endpoint**. The platform supports update semantics (UPSERT), not duplication.

**Current state:**
- **DB:** `UNIQUE (vendor_code, operation_code, flow_direction) WHERE is_active = true`
- **Backend:** Both registry and vendor lambdas use `ON CONFLICT ... DO UPDATE` for true UPSERT.
- **Seed:** Uses SELECT-by-(vendor, op, direction) then UPDATE or INSERT for baseline reset.

**Status:** Aligned. No changes needed.

---

## 2. Feature Gates Baseline ✅

**Design expectation:** Feature gates are global toggles or per-vendor overrides, both updateable. Seed should enforce authoritative baseline.

**Current state:**
- **DB:** `UNIQUE (feature_code) WHERE vendor_code IS NULL` for global gates.
- **Backend:** Admin PUT uses `ON CONFLICT DO UPDATE`.
- **Seed:** Uses `ON CONFLICT (feature_code) WHERE (vendor_code IS NULL) DO UPDATE SET is_enabled = EXCLUDED.is_enabled`.

**Status:** Aligned. Seed correctly treats gates as authoritative baseline.

---

## 3. GET_RECEIPT Direction Policy ✅

**Design expectation:** `GET_RECEIPT` is PROVIDER_RECEIVES_ONLY (caller → provider; provider receives only).

**Current state:**
- **Seed:** `direction_policy="PROVIDER_RECEIVES_ONLY"` for GET_RECEIPT.
- **Backend:** Routing and readiness use direction_policy correctly.

**Status:** Aligned.

---

## 4. Canonical Pass-Through Convention

**Design expectation:** If a vendor has *no* vendor override schema, the system treats it as **canonical pass-through**.

**Convention (no schema change):**
- `vendor_operation_contracts` row present and active → vendor override
- No row (or inactive) → canonical contract is used (pass-through)

**Backend:** `contract_utils.load_effective_contract()` implements this: vendor override first, then canonical fallback.

**Status:** Convention adopted. No DB change required.

---

## 5. Wildcard Allowlist Semantics ✅

**Design expectation:**
- `* → LH001` = inbound only (anyone can call me)
- `LH001 → *` = outbound only (I can call anyone)

**Current state:** Vendor API `_handle_get_my_allowlist` applies:
- Outbound: rules where `(source=me OR is_any_source)` AND `flow_direction IN ('OUTBOUND','BOTH')`, excluding `*→me`-only rules.
- Inbound: rules where `(target=me OR is_any_target)` AND `flow_direction IN ('INBOUND','BOTH')`, excluding `me→*`-only rules.

**Status:** Logic verified correct.

---

## 6. vendor_supported_operations vs Allowlist

**Design expectation:** Allowlist + canonical contract = source of truth for access. `vendor_supported_operations` is for **capability listing** (what the vendor can configure).

**Current state:**
- My-operations / eligible-operations combine allowlist rules with vendor-supported-ops flags.
- `supports_outbound` / `supports_inbound` describe vendor capability; allowlist describes admin-permitted access.

**Unified rule:** Use allowlist + canonical contract for routing/execute decisions; use `vendor_supported_operations` only for UI capability display and flow-builder eligibility.

**Status:** Documented. Logic already aligned in most places; ensure new code follows this rule.

---

## 7. Endpoint verification_status Lifecycle

**Design expectation:** Clear lifecycle and transitions.

| Status    | Meaning                                                |
|----------|---------------------------------------------------------|
| PENDING   | Default; not yet verified                               |
| VERIFIED | Verification succeeded                                  |
| FAILED   | Verification attempted and failed                        |

**Transitions:**
- INSERT → PENDING
- POST /endpoints/verify success → VERIFIED
- POST /endpoints/verify failure → FAILED
- Endpoint URL/http_method/payload_format change → PENDING (vendor_registry already does this via CASE in upsert)
- Optional future: VERIFIED → PENDING after TTL (e.g. `EXPIRED`) – not yet implemented

**Status:** Lifecycle documented. Backend already implements PENDING/VERIFIED/FAILED.

---

## 8. Vendor Portal → Vendor API Only ✅

**Design expectation:** Vendor portal talks **only** to Vendor API.

**Current state:**
- Vendor portal uses `vendorApi` from `createClients.ts`. No `adminApi` usage.
- Vendor API serves canonical operations and contracts from DB (`_list_canonical_operations_db`, `_list_canonical_contracts_db`). No Admin API dependency.

**Status:** Aligned.

---

## 9. Change Request Model

**Current tables:**
- `change_requests` – legacy/admin-originated (used by `approval_utils.apply_change_request`)
- `vendor_change_requests` – vendor-originated (endpoint, mapping, contract, allowlist edits)
- `allowlist_change_requests` – allowlist-specific vendor requests

**Unified semantics:**
- **Vendor-originated:** Vendor portal creates `vendor_change_requests` or `allowlist_change_requests` based on request type.
- **Admin approval:** Admin uses `/v1/registry/change-requests` which queries both `allowlist_change_requests` and `vendor_change_requests` by source.
- **Apply flow:** `apply_vendor_change_request` and `apply_allowlist_change_request` materialize approved changes.

**Status:** Fragmented but functional. Full unification would require schema consolidation; current workflow is documented.

---

## 10. Vendor Auth Profile Linking Invariant

**Design expectation:** If auth is required for the endpoint, `vendor_auth_profile_id` must be non-null.

**Current state:**
- `vendor_auth_profile_id` is optional on `vendor_endpoints`.
- No explicit `requires_auth` flag on endpoints.
- When `vendor_auth_profile_id` is set, it must reference a valid row in `control_plane.vendor_auth_profiles` for the endpoint vendor.
- Legacy `auth_profile_id` is retained for backward compatibility only and is not used by active runtime resolution.

**Rule:** When `vendor_auth_profile_id` is provided, it must reference a vendor auth profile belonging to the vendor. The inverse ("auth required → must have profile") would require a new `requires_auth` or equivalent on endpoints.

**Recommendation:** Add application-level validation: if an endpoint targets a URL pattern that suggests a secured API (e.g. non-public domains) and `vendor_auth_profile_id` is null, log a warning. Hard enforcement needs schema change.

**Status:** Documented. Validation exists for "profile exists and belongs to vendor" when provided.

---

## Summary

| Issue                      | Status  | Action                                         |
|----------------------------|---------|------------------------------------------------|
| Endpoint uniqueness        | ✅ Fixed | Backend already UPSERT                         |
| Feature gates baseline     | ✅ Fixed | Seed already UPSERT                           |
| GET_RECEIPT policy         | ✅ Fixed | Seed uses PROVIDER_RECEIVES_ONLY               |
| Canonical pass-through     | Doc     | Convention adopted                             |
| Wildcard allowlist         | ✅ Fixed | Logic verified correct                         |
| Supported ops vs allowlist | Doc     | Documented source of truth                     |
| Verification lifecycle     | Doc     | PENDING/VERIFIED/FAILED defined                |
| Vendor API canonical reads | ✅ Fixed | Vendor API owns reads                          |
| Change request model       | Doc     | Workflow documented                            |
| Auth profile linking       | Doc     | Validation when provided; full rule needs schema |
