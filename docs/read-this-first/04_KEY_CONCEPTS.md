# Key Concepts

Core concepts that govern how the Integration Hub works. These invariants must be respected when coding.

---

## 1. Effective Contract

**Rule:** Use `load_effective_contract(flow_direction)` everywhere. Never load contracts directly from tables without direction resolution.

| Scenario | Effective Contract |
|----------|-------------------|
| Vendor contract exists for direction | Vendor contract |
| No vendor contract | Canonical contract |
| Neither exists | Return `CONTRACT_NOT_FOUND` |

- Vendor contracts can override canonical **per direction** (OUTBOUND/INBOUND).
- Request/response payloads must validate against the **effective** contract.
- When canonical-only and no mapping exists → **canonical pass-through** is valid.

---

## 2. Effective Mapping

**Rule:** Determine via `resolve_effective_mapping(flow_direction)`.

| Scenario | Effective Mapping |
|----------|-------------------|
| Vendor mapping exists | Vendor mapping |
| No vendor mapping, payload fits canonical | Canonical pass-through (no error) |
| Mapping required (e.g. vendor contract override) but missing | Return mapping error |

**UI feedback:** If canonical pass-through is used → show "Using canonical format", not "Missing mapping".  
**Approval:** If mapping edits are gated, vendor changes create a **change-request** for admin approval.

---

## 3. Effective Endpoint

**Rule:** Use `load_effective_endpoint(operation, vendor, flow_direction)`.

| Scenario | Result |
|----------|--------|
| Active endpoint exists for (vendor, operation, direction) | That endpoint |
| No active endpoint | `ENDPOINT_NOT_FOUND` |

- Only consider endpoints where `is_active = true`.
- **OUTBOUND**: vendor → external
- **INBOUND**: external → vendor
- Endpoint health does not block execution unless explicitly gated.

---

## 4. Allowlist & Access

**Rule:** Access is determined by `(source_vendor, target_vendor, operation)` rules.

| Flow | Vendor Role |
|------|-------------|
| OUTBOUND | Vendor is **source** |
| INBOUND | Vendor is **target** |

- Wildcards allowed: `source="*"`, `target="*"`.
- Effective access: direct rule OR wildcard rule OR admin gating/approval status.
- If outbound blocked → `ACCESS_DENIED`.

---

## 5. Direction Semantics

**Flow direction** must be derived **once** and passed consistently through the entire execute pipeline.

| Direction | Meaning | Example |
|-----------|----------|---------|
| OUTBOUND | Caller → Provider | LH001 calls LH002 |
| INBOUND | External → Vendor | LH002 receives from LH001 |
| BOTH | Two-way (allowlist) | LH001 ↔ LH002 for same operation |

---

## 6. Vendor Identity (JWT Only)

- **Source of truth:** JWT from Auth0.
- **Vendor code:** From a single JWT claim (e.g. `vendor_code`).
- **Never** take vendor identity from: headers, query params, or body fields.
- **No API keys** for vendor identity. Internal service-to-service may use secrets/IAM.

---

## 7. Feature Gates

Feature gates control whether vendor edits are **direct-write** or **admin-approved**.

| Gate | Affects |
|------|---------|
| `mapping_edit` | Mapping changes |
| `contract_edit` | Contract changes |
| `endpoint_edit` | Endpoint changes |
| `allowlist_edit` | Allowlist changes |

- Gates do **not** affect authentication.
- Gates do **not** influence vendor identity.

---

## 8. includeActuals

When `includeActuals=true`, the response **always** includes actual request/response payloads for debugging. Invariant: never omit when requested.

---

## 9. Canonical Error Model

All errors must include the canonical error model (code, message, details). Use helpers from `canonical_error.py` (e.g. `auth_error`, `allowlist_denied`, `endpoint_not_found`).

---

## 10. Empty DB

Fresh prod environments may have no data. All list endpoints return `200` with `items: []`. No 500s from missing tables or empty results.

---

Next: [05_RUNTIME_FLOW.md](05_RUNTIME_FLOW.md)
