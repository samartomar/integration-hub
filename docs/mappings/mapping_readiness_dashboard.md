# Mapping Readiness Dashboard

## Overview

The Mapping Readiness Dashboard provides **read-only visibility** into canonical mapping coverage and readiness across operation/vendor pairs. It derives status from existing code-first artifacts. No persistence. No runtime execution. No automatic apply.

## Readiness Model

Readiness is derived from:

1. **Mapping definition** – Does the canonical mapping engine have a mapping for this operation/vendor pair?
2. **Fixtures** – Are fixture cases registered for certification?
3. **Certification** – Do both directions (CANONICAL_TO_VENDOR, VENDOR_TO_CANONICAL) pass certification?
4. **Runtime ready** – Is the mapping available for runtime use? (Same as mapping definition for code-first engine.)

## Status Values

| Status | Meaning |
|--------|---------|
| **READY** | Mapping definition + fixtures + certification passes + runtime integration. Fully production-ready. |
| **IN_PROGRESS** | Some artifacts present, some missing. Work in progress. |
| **MISSING** | No mapping definition. Not yet implemented. |
| **WARN** | Mapping and fixtures exist but certification fails. Needs attention. |

## How Readiness Is Derived

- **Mapping definition**: `get_mapping_definition(operation, version, source, target)` returns non-null.
- **Fixtures**: `list_mapping_fixtures(...)` returns non-empty list.
- **Certification**: `run_mapping_certification` for both directions returns `valid=True` and `failed=0`.
- **Runtime ready**: Same as mapping definition (engine is the runtime integration).

The service is conservative: it does not fabricate readiness. Only actual code-first artifacts are considered.

## API Endpoints

- **GET /v1/mappings/canonical/readiness** – List readiness items, optionally filtered by:
  - `operationCode`
  - `sourceVendor`
  - `targetVendor`
  - `status`
- **GET /v1/mappings/canonical/readiness/{operationCode}** – Readiness for that operation across vendor pairs.

## Scaling Onboarding

The dashboard supports scaling by:

1. **Visibility** – See which mappings are READY vs IN_PROGRESS vs MISSING at a glance.
2. **Prioritization** – Focus on MISSING or WARN items.
3. **Consistency** – Same readiness criteria across all operation/vendor pairs.
4. **Integration** – Works with Scaffold Generator (generate scaffold for MISSING) and Certification (fix WARN).

## Related

- [Mapping Certification Workflow](mapping_certification_workflow.md)
- [Mapping Scaffold Onboarding Workflow](mapping_scaffold_onboarding_workflow.md)
- [Canonical Mapping Engine](canonical_mapping_engine.md)
