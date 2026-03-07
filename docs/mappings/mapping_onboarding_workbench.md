# Mapping Onboarding Workbench

## Overview

The Mapping Onboarding Workbench turns the [Mapping Readiness Dashboard](mapping_readiness_dashboard.md) into an operational surface. It derives **deterministic next-action recommendations** from readiness state and links them to the existing [Canonical Mapping Page](canonical_mapping_engine.md) workflows. No persistence. No runtime mutation. Admin-only.

## Where It Fits

After readiness shows what is READY vs missing/partial, the workbench answers: **what should an admin do next for each row?**

- **Readiness** → coverage and status (READY, IN_PROGRESS, MISSING, WARN)
- **Onboarding Workbench** → recommended next action + deep-link to Canonical Mappings with prefill

## Design Principles

1. **Deterministic** – Actions are derived from readiness only, not AI-generated
2. **Read-only** – No mutation from the workbench; it orchestrates navigation
3. **Reuse** – Links into existing scaffold, suggest, proposal, promotion, certification flows
4. **No automatic apply** – Admin performs actions manually

## Next Action Model

| Readiness Status | Condition | Next Action |
|------------------|-----------|-------------|
| READY | — | READY |
| MISSING | No mapping definition | GENERATE_SCAFFOLD |
| IN_PROGRESS | Mapping exists, no fixtures | ADD_FIXTURES |
| IN_PROGRESS | Mapping + fixtures, cert not passing | RUN_CERTIFICATION |
| IN_PROGRESS | Fixtures exist, no mapping | COMPLETE_MAPPING_DEFINITION |
| IN_PROGRESS | Partial artifacts | COMPLETE_MAPPING_DEFINITION |
| WARN | Mapping + fixtures, cert failed | INVESTIGATE_WARN |
| WARN | Inconsistent state | REVIEW_PROMOTION_ARTIFACT |

## API Endpoints

- **GET /v1/mappings/canonical/onboarding-actions** – List readiness-derived action items
- **GET /v1/mappings/canonical/onboarding-actions/{operationCode}** – Actions for that operation

Query params: `operationCode`, `sourceVendor`, `targetVendor`, `status`, `nextAction`

## Response Shape

Each item includes readiness fields plus `nextAction`:

```json
{
  "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
  "version": "1.0",
  "sourceVendor": "LH001",
  "targetVendor": "LH003",
  "status": "MISSING",
  "nextAction": {
    "code": "GENERATE_SCAFFOLD",
    "title": "Generate scaffold bundle",
    "description": "No mapping definition exists yet for this vendor pair.",
    "targetRoute": "/admin/canonical-mappings",
    "prefill": {
      "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
      "version": "1.0",
      "sourceVendor": "LH001",
      "targetVendor": "LH003"
    }
  },
  "notes": ["Recommended action is derived from deterministic readiness only."]
}
```

## Deep-Link / Prefill

When an admin clicks a next-action button on the Readiness page:

1. Navigate to `/admin/canonical-mappings`
2. Pass `prefill` via React Router `state`
3. Canonical Mapping Page reads `location.state.prefill` (or query params)
4. Prefills: operationCode, sourceVendor, targetVendor, version
5. Admin can immediately run Scaffold, Suggest, Certification, etc.

Query params are also supported: `?operationCode=X&sourceVendor=Y&targetVendor=Z&version=1.0`

## Suggested Operator Flow

1. **View readiness** – Open Mapping Readiness dashboard
2. **Take recommended action** – Click next-action button for a row
3. **Scaffold / define / fixture / certify / promote** – Use Canonical Mappings (prefilled)
4. **Rerun readiness** – Refresh dashboard to see updated status

## Related

- [Mapping Readiness Dashboard](mapping_readiness_dashboard.md)
- [Mapping Scaffold Onboarding Workflow](mapping_scaffold_onboarding_workflow.md)
- [Mapping Certification Workflow](mapping_certification_workflow.md)
- [Canonical Mapping Engine](canonical_mapping_engine.md)
