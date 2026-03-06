# Regression Test Plan – Service Portal UI Stabilization

## Scope

Tests-only PR. No production code changes. Lock in:
- Configuration Overview vs Flow Builder status alignment
- Endpoint status derivation (inbound missing-endpoint case)
- Version label formatting (`formatVersionLabel`)
- Direction-aware endpoint copy (inbound vs outbound)

---

## 1) Target Test Files

| File | Action |
|------|--------|
| `src/utils/readinessModel.test.ts` | Extend – add `toEndpointStatus` Outbound cases; add regression readiness scenario |
| `src/utils/flowReadiness.test.ts` | Extend – add `formatVersionLabel` edge cases |
| `src/pages/VendorFlowBuilderPage.test.tsx` | Extend – add operation info panel status tests; add direction-aware endpoint copy tests |
| `src/pages/VendorConfigurationPage.test.tsx` | Extend – add partial-config fixture and chip status assertions |
| `src/components/EndpointSummaryPanel.test.tsx` | **New** – unit test for direction-aware empty-state copy (if panel is testable in isolation with mocks) |

---

## 2) Cases to Cover

### P0 — Status Logic Regression

#### 2.1 `toEndpointStatus` behavior matrix (`readinessModel.test.ts`)

| Case | hasEndpoint | endpointVerified | direction | Expected |
|------|-------------|------------------|-----------|----------|
| Inbound + endpoint + verified | true | true | Inbound | configured |
| Inbound + endpoint + not verified | true | false | Inbound | partial |
| Inbound + no endpoint | false | false | Inbound | **missing** (regression) |
| Outbound + endpoint + verified | true | true | Outbound | configured |
| Outbound + endpoint + not verified | true | false | Outbound | partial |
| Outbound + no endpoint | false | false | Outbound | missing |

**New tests:**
- `toEndpointStatus returns configured when endpoint verified for Outbound`
- `toEndpointStatus returns partial when endpoint not verified for Outbound`

*Note: Inbound missing case already exists. All four Outbound cases are covered (missing exists; add configured/partial).*

#### 2.2 Readiness row – partial config regression (`readinessModel.test.ts`)

**Scenario (previously regressed):**
- Contract: configured
- Endpoint: missing
- Mapping: missing
- Access: allowed
- Overall: `config_missing` (Needs configuration)

**New test:**
- `inbound partial config: contract configured, endpoint missing, mapping missing, access allowed, overall needs configuration`

**Fixture:** Inbound operation, vendor contract present, no endpoints, no inbound mappings, allowlist permits inbound. Assert: `hasContract=true`, `hasEndpoint=false`, `hasMapping=false`, `hasAccess=true`, `overallStatus=config_missing`, and derived `toEndpointStatus(row)...` yields `missing`.

---

### P1 — UI Alignment Regression

#### 2.3 Flow Builder operation info panel (`VendorFlowBuilderPage.test.tsx`)

**Fixture:** Same semantics as partial-config scenario:
- `getVendorContracts` → `{ items: [{ operationCode: "GET_RECEIPT" }] }`
- `getVendorEndpoints` → `{ items: [] }`
- `getVendorMappings` → `{ mappings: [] }`
- `getMyAllowlist` → access allowed for GET_RECEIPT inbound
- `getVendorSupportedOperations` → GET_RECEIPT supportsInbound

**Assert:** Operation info panel shows:
- Contract: Configured (or chip label "Configured")
- Endpoint: Missing (or chip label "Missing")

**New test:**
- `flow builder operation info shows endpoint missing when readiness has no endpoint`

Optional second fixture (all configured) to assert Configured for all chips.

#### 2.4 Configuration Overview (`VendorConfigurationPage.test.tsx`)

**Fixture:** Same partial-config. Mock:
- `getVendorContracts` → `{ items: [{ operationCode: "GET_RECEIPT" }] }`
- `getVendorEndpoints` → `{ items: [] }`
- `getVendorMappings` → `{ mappings: [] }`
- `getMyAllowlist` → inbound allowlist entry for GET_RECEIPT
- `getVendorSupportedOperations` → GET_RECEIPT with supportsInbound
- Catalog, myOperations as needed

**Assert:** Table row for GET_RECEIPT Inbound shows:
- Contract pill: Configured
- Endpoint pill: Missing
- Mapping pill: Missing
- Overall: Needs configuration

**New test:**
- `overview row shows endpoint missing when fixture has no endpoint for partial config`

---

### P1 — Version Formatting Regression

#### 2.5 `formatVersionLabel` (`flowReadiness.test.ts`)

| Case | Input | Expected |
|------|-------|----------|
| vv1 duplication | `vv1` | `v1` |
| V1 (uppercase) | `V1` | `v1` |
| Whitespace-padded | ` v1 ` | `v1` |
| v01 | `v01` | `v01` (or `v1` – assert current behavior) |
| 1.0 | `1.0` | `v1.0` (assert current behavior) |

**New tests:**
- `normalizes uppercase v prefix (V1)`
- `trims whitespace before normalizing`
- (Optional) `handles v01`, `handles 1.0` – assert existing behavior, no behavior change.

---

### P1 — Direction-Aware Endpoint Copy Regression

#### 2.6 EndpointSummaryPanel direction copy (`EndpointSummaryPanel.test.tsx` – new file, or within `VendorFlowBuilderPage.test.tsx`)

**Option A – Isolated component test:**  
Render `EndpointSummaryPanel` with `direction="inbound"` and `direction="outbound"`, mock endpoints empty. Assert:
- Inbound: text includes "Other licensees call your API"
- Outbound: text includes "routes your request" and "target licensee"

**Option B – Via Flow Builder:**  
Render Flow Builder at `/builder/GET_RECEIPT/v1?direction=inbound` and `/builder/GET_RECEIPT/v1?direction=outbound`, click to Endpoint stage, assert same substrings.

**New tests:**
- `inbound endpoint empty state shows other licensees call your API`
- `outbound endpoint empty state shows routing to target licensee API`

---

### P2 — Guardrails

#### 2.7 Mock stability

VendorFlowBuilderPage tests already mock:
- `getVendorContracts`, `getVendorEndpoints`, `getVendorMappings`

No additional mocks required. VendorConfigurationPage already mocks all needed APIs.

#### 2.8 Warnings cleanup

Existing mocks appear complete. If any test emits "Query data cannot be undefined" for new queries, add the corresponding mock in `beforeEach` only.

---

## 3) Mock Strategy

### Shared partial-config fixture (semantic parity)

```ts
// Concept – same data shape for both Overview and Flow Builder
PARTIAL_CONFIG_FIXTURE = {
  vendorContracts: [{ operationCode: "GET_RECEIPT" }],
  endpoints: [],
  mappings: [],
  supported: [{ operationCode: "GET_RECEIPT", supportsInbound: true, supportsOutbound: false }],
  catalog: [{ operationCode: "GET_RECEIPT", canonicalVersion: "v1" }],
  allowlist: { inbound: [{ sourceVendor: "*", targetVendor: "LH001", operation: "GET_RECEIPT" }], outbound: [] },
}
```

- **Overview:** Map to `getVendorContracts`, `getVendorEndpoints`, `getVendorMappings`, `getMyAllowlist`, etc.
- **Flow Builder:** Same API mocks + `getFlow`, `getOperationMappings` as needed.

### Direction param for Flow Builder

- Use `initialEntries={["/builder/GET_RECEIPT/v1?direction=inbound"]}` or `?direction=outbound` to drive `directionFromUrl` and thus EndpointSummaryPanel `direction` prop.

---

## 4) Risk Check

- **No production code changes** – only test files and possibly a shared fixture/helper in test code.
- **No selector/readiness logic changes** – tests assert current behavior.
- **No API/query/fetch changes** – mocks only.
- **Possible test-only export** – If EndpointSummaryPanel requires heavy provider/context setup, prefer Flow Builder integration tests over adding a testability export. Document any exception.

---

## 5) Test Naming (examples)

- `toEndpointStatus returns configured when endpoint verified for Outbound`
- `toEndpointStatus returns partial when endpoint not verified for Outbound`
- `inbound partial config yields needs configuration when endpoint and mapping missing`
- `flow builder operation info shows endpoint missing when readiness has no endpoint`
- `overview row shows endpoint missing when fixture has no endpoint for partial config`
- `formatVersionLabel normalizes uppercase v prefix`
- `formatVersionLabel trims whitespace`
- `inbound endpoint helper text references other licensees calling your API`
- `outbound endpoint helper text references routing to target licensee API`
