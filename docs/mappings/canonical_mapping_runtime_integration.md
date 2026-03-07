# Canonical Mapping Runtime Integration

The deterministic Canonical Mapping Engine is now integrated into the canonical preflight and canonical bridge execution path. This document describes how the integration works and what changed.

## Overview

- **Canonical model** remains the source of truth.
- **Mapping definitions** remain adapters (code-first in `canonical_mappings/`).
- **Existing runtime execute path** remains the executor—no new execution engine was introduced.
- **Canonical bridge** is now mapping-aware: it validates and previews transforms before execution.
- **Deterministic mappings** are authoritative; no LLM-generated mapping logic in this step.

## Integration Points

### 1. Preflight (mapping-aware)

`run_canonical_preflight` now:

- Resolves mapping definition via `canonical_mapping_engine.get_mapping_definition()`
- Validates canonical payload can be transformed to vendor request via `transform_canonical_to_vendor()`
- Adds checks: `MAPPING_DEFINITION_FOUND`, `CANONICAL_TO_VENDOR_TRANSFORM_VALID`
- Returns additive fields when mapping exists:
  - `mappingSummary`: `{ available, direction, fieldMappings, warnings }`
  - `vendorRequestPreview`: safe preview of the mapped vendor request payload

**Behavior when no mapping exists:** Preflight returns `MAPPING_DEFINITION_FOUND` WARN (not BLOCKED). Execution can still proceed if the existing runtime has DB-based mappings.

**Behavior when transform fails:** Missing required canonical fields for the mapping yield `CANONICAL_TO_VENDOR_TRANSFORM_VALID` FAIL and status BLOCKED.

### 2. Bridge (mapping-aware)

`run_canonical_bridge` now:

- Runs preflight first (unchanged)
- For **DRY_RUN**: includes `mappingSummary` and `vendorRequestPreview` from preflight
- For **EXECUTE**:
  - Passes canonical payload to the existing execute path (no change to what is sent)
  - When the execute path returns `responseBody` (canonical response), surfaces it as `canonicalResponseEnvelope`
  - When the response body is vendor-shaped and a mapping exists, attempts `transform_vendor_to_canonical()` and adds `canonicalResponseEnvelope` when successful
  - If reverse mapping cannot be applied, keeps `executeResult` as-is and adds a note

**Important:** The bridge does not replace the execute path. It continues to call the existing runtime with canonical parameters. The routing lambda performs its own DB-based mapping. Our engine provides deterministic validation and preview.

### 3. Reverse Mapping

For supported operations (GET_VERIFY_MEMBER_ELIGIBILITY, GET_MEMBER_ACCUMULATORS) and vendor pairs (LH001→LH002):

- When the execute path returns a body with `responseBody`, that is already the canonical response from the routing pipeline—the bridge surfaces it as `canonicalResponseEnvelope`
- When the body is vendor-shaped (e.g. from a different code path), the bridge attempts `transform_vendor_to_canonical()` and adds `canonicalResponseEnvelope` only when the transform succeeds with no violations
- When reverse mapping cannot be applied (missing structure, unsupported shape), the bridge returns a note and preserves `executeResult`

### 4. Flow Runtime Handoff

When `runPreflight` is true, the handoff calls `run_canonical_preflight`. The preflight result now includes mapping-aware fields (`mappingSummary`, `vendorRequestPreview`). No changes to the handoff API were required.

### 5. Registry Lambda

The preflight and execute handlers now derive `mapping_ok` from the engine when possible: `mapping_ok = get_mapping_definition(op_code, resolved, source, target) is not None`. This populates the `RUNTIME_MAPPING_FOUND` check.

## No New Runtime Engine

- No parallel execution path
- No direct vendor call logic outside the existing execute path
- Canonical → vendor transform is used for **preview and validation**; the actual execution still uses the routing lambda’s DB-based mapping
- Future work could wire the engine’s transformed payload into the execute request when desired

## Files Changed

| Area | Files |
|------|-------|
| Preflight | `apps/api/src/schema/canonical_runtime_preflight.py` |
| Bridge | `apps/api/src/schema/canonical_runtime_bridge.py` |
| Registry | `apps/api/src/lambda/registry_lambda.py` |
| Admin UI | `apps/web-cip/src/pages/RuntimePreflightPage.tsx`, `CanonicalExecutePage.tsx`, `FlowBuilderPage.tsx` |
| API types | `apps/web-cip/src/api/endpoints.ts` |
| Tests | `tests/schema/test_canonical_runtime_preflight.py`, `test_canonical_runtime_bridge.py` |

## Suggested Commit Message

```
feat(runtime): integrate deterministic canonical mappings into preflight and bridge execution
```
