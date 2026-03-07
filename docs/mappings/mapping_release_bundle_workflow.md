# Mapping Release Bundle Workflow

## Overview

The Mapping Release Bundle workflow groups **multiple READY mappings** into a single review artifact for release planning and coordination. It answers: *What mappings are we releasing together, and what files/checklists apply?* No persistence. No runtime mutation. Admin-only. Review-only.

## Difference from Per-Mapping Release Readiness

| Aspect | Per-Mapping Release Readiness | Release Bundle |
|--------|------------------------------|----------------|
| Scope | Single operation/vendor pair | Multiple pairs |
| Purpose | Is this mapping ready? | What are we releasing together? |
| Output | Report + markdown | Bundle summary, impacted files, checklist |
| Use | Pre-promotion review | Release coordination, code review planning |

## Design Principles

1. **Deterministic** – Bundle derived from existing readiness/release-readiness
2. **Read-only** – No mutation; artifact only
3. **Batch-level** – Groups multiple mappings for coordinated release
4. **No automatic apply** – Human performs code review and promotion manually

## How Bundle Candidates Are Derived

Candidates come from **release readiness** (which derives from mapping readiness):

- `list_release_bundle_candidates(filters)` → calls `list_mapping_release_readiness(filters)`
- Filters: `operationCode`, `sourceVendor`, `targetVendor`, `status`, `readyForPromotion`
- Only READY / `readyForPromotion=true` mappings are ideal candidates, but admins may include non-ready items (bundle status becomes BLOCKED)

## Bundle Generation

**Input payload:**

```json
{
  "bundleName": "Release Candidate 2026-03-07",
  "items": [
    {
      "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
      "version": "1.0",
      "sourceVendor": "LH001",
      "targetVendor": "LH002"
    }
  ]
}
```

**Output:**

- `bundleId`, `bundleName`, `createdAt`
- `summary`: included, ready, blocked, status (READY | BLOCKED)
- `items`: each with readyForPromotion, status, targetDefinitionFile, evidence, blockers
- `impactedFiles`: inferred from naming conventions
- `verificationChecklist`: manual review steps
- `markdown`: full markdown artifact

Bundle status is **READY** only when all selected items are `readyForPromotion=true`. Any blocked item makes the bundle **BLOCKED**.

## API Endpoints

- **GET /v1/mappings/canonical/release-bundle/candidates** – List candidate mappings
- **POST /v1/mappings/canonical/release-bundle** – Generate structured bundle (includes markdown)
- **POST /v1/mappings/canonical/release-bundle/markdown** – Generate markdown artifact only

## Recommended Operator Flow

1. **Readiness** – View Mapping Readiness dashboard
2. **Next action** – Use Onboarding Workbench to scaffold, add fixtures, run certification
3. **Certification** – Ensure certification passes for each mapping
4. **Release readiness** – Generate per-mapping release report for READY rows
5. **Release bundle** – Select READY rows, generate bundle for coordinated release
6. **Manual code review** – Complete verification checklist, commit, promote

## UI Integration

On the Mapping Readiness page:

- **Bundle column** – Checkbox to select rows for bundle
- **Generate Release Bundle** – Builds full bundle (summary, items, impacted files, checklist, markdown)
- **Generate Release Bundle Markdown** – Same as above (bundle endpoint returns markdown)

The bundle panel shows summary, included items, blockers, impacted files, verification checklist, and markdown artifact. No Apply or Promote button. This is review-only.
