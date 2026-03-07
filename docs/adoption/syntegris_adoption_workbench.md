# Adoption Workbench

## Overview

The **Adoption Workbench** is an admin visibility layer that shows:

1. **What already exists** in the Integration Hub (integration inventory)
2. **How far** each operation/vendor pair has been adopted

It is an adoption/visibility layer on top of the existing system, not a runtime rewrite. No persistence. No mutation. Read-only.

**Note:** API paths (`/v1/syntegris/*`), route `/admin/syntegris-adoption`, and internal identifiers may retain legacy naming for backward compatibility. User-facing labels use neutral terms (Adoption, Ready, etc.).

## Integration Inventory

Inventory is discovered from `vendor_operation_allowlist` (explicit pairs only). For each pair, the system checks:

| Evidence | Meaning |
|----------|---------|
| `operationExists` | Operation is registered in the canonical registry |
| `allowlistExists` | Allowlist rule exists for source→target |
| `operationContractExists` | Canonical contract exists for the operation |
| `vendorMappingExists` | Vendor mapping is configured |
| `endpointConfigExists` | Endpoint is configured for the direction |

## Adoption Classification

Adoption status is derived from inventory evidence plus Syntegris artifacts (canonical mapping, certification, release readiness). Statuses:

| Status | Meaning |
|--------|---------|
| **LEGACY_ONLY** | Allowlist exists but no canonical contract or mapping |
| **CANON_DEFINED** | Canonical contract exists, mapping not yet started |
| **MAPPING_IN_PROGRESS** | Mapping in progress, not certified |
| **CERTIFIED** | Mapping certified, not yet release-ready |
| **RELEASE_READY** | Release-ready, not yet runtime-integrated |
| **SYNTEGRIS_READY** (Ready) | Fully adopted (LH001→LH002 for supported ops) |
| **BLOCKED** | Blocked by missing artifacts or errors |

## Supported Slice

The current production-mature slice is:

- **Operations:** `GET_VERIFY_MEMBER_ELIGIBILITY`, `GET_MEMBER_ACCUMULATORS`
- **Vendor pair:** LH001 → LH002

Pairs in this slice can reach `SYNTEGRIS_READY` when all evidence is in place.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/syntegris/inventory` | List integration inventory (filterable) |
| GET | `/v1/syntegris/inventory/{operationCode}` | Inventory for an operation |
| GET | `/v1/syntegris/adoption` | List adoption items (filterable) |
| GET | `/v1/syntegris/adoption/summary` | Adoption counts by status |
| GET | `/v1/syntegris/adoption/{operationCode}` | Adoption for an operation |

### Query Parameters (inventory)

- `operationCode`, `sourceVendor`, `targetVendor`
- `hasAllowlist`, `hasOperationContract`, `hasVendorMapping`, `hasEndpointConfig` (boolean)

### Query Parameters (adoption)

- `operationCode`, `sourceVendor`, `targetVendor`
- `adoptionStatus`, `nextAction`

## Admin UI

- **Route:** `/admin/syntegris-adoption`
- **Nav:** "Syntegris Adoption" in TopBar

Features:

- Summary cards for adoption counts
- Filters: operation, source vendor, target vendor, adoption status, next action
- Table with inventory evidence, adoption status, next action
- Detail panel with evidence, notes, and deep links

## Deep Links

The workbench provides deep links to related admin pages with pre-filled query params:

- `operationCode`, `version`, `sourceVendor`, `targetVendor`

Target pages that support prefill:

- Canonical Mappings (`/admin/canonical-mappings`)
- Mapping Readiness (`/admin/canonical-mapping-readiness`)
- Flow Builder (`/admin/flow-builder`)
- Runtime Preflight (`/admin/runtime-preflight`)
- Canonical Execute (`/admin/canonical-execute`)

## Related

- [Feature Production Readiness](../release/syntegris_feature_production_readiness.md)
- [Mapping Readiness Dashboard](../mappings/mapping_readiness_dashboard.md)
- [Mapping Onboarding Workbench](../mappings/mapping_onboarding_workbench.md)
