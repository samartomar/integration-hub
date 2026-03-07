# Mapping Release Readiness Workflow

## Overview

The Mapping Release Readiness workflow provides a **deterministic release confidence report** for mappings that are READY. It answers: *Is this mapping ready for human code promotion and rollout?* No persistence. No runtime mutation. Admin-only. Review-only.

## Where It Fits

After the [Mapping Onboarding Workbench](mapping_onboarding_workbench.md) identifies next actions and mappings reach READY status, the release readiness report provides a **reviewable artifact** before manual code promotion decisions.

- **Readiness Dashboard** → coverage and status (READY, IN_PROGRESS, MISSING, WARN)
- **Onboarding Workbench** → next action (scaffold, fixtures, certify, etc.)
- **Release Readiness Report** → release confidence, blockers, checklist, recommended next step

## Design Principles

1. **Deterministic** – Derived from existing readiness, certification, and runtime signals
2. **Read-only** – No mutation; report only
3. **Conservative** – Does not fabricate readiness; explicit blockers when not ready
4. **No automatic apply** – Human performs code review and promotion manually

## Release-Ready Criteria

A mapping is `readyForPromotion` when all of the following are true:

- `mappingDefinition` = true
- `fixtures` = true
- `certification` = true
- `runtimeReady` = true
- `status` from readiness = READY
- No blockers

If any criterion fails, the report lists explicit **blockers** (e.g., "No mapping definition.", "No fixtures.", "Certification not passing.").

## API Endpoints

- **GET /v1/mappings/canonical/release-readiness** – List release readiness rows
- **POST /v1/mappings/canonical/release-readiness/report** – Generate detailed report for a pair
- **POST /v1/mappings/canonical/release-readiness/report/markdown** – Generate markdown artifact

Query params for GET: `operationCode`, `sourceVendor`, `targetVendor`, `status`, `readyForPromotion`

## Report Output

The report includes:

- `readyForPromotion` – boolean
- `blockers` – list of strings
- `evidence` – mappingDefinition, fixtures, certification, runtimeReady
- `releaseChecklist` – manual review steps
- `recommendedNextStep` – e.g., "Manual code review and promotion." or "Address blockers before promotion."
- `notes` – e.g., "Release report only. No code or runtime state was changed."

## Difference from Readiness Dashboard

| Aspect | Readiness Dashboard | Release Readiness Report |
|--------|---------------------|--------------------------|
| Purpose | Coverage and status | Release confidence |
| Scope | All pairs | Single pair (for report) |
| Output | List with status | Detailed report + markdown |
| Use | Identify gaps | Pre-promotion review |

## Recommended Operator Flow

1. **Readiness** – View Mapping Readiness dashboard
2. **Next action** – Use Onboarding Workbench to scaffold, add fixtures, run certification
3. **Certification** – Ensure certification passes
4. **Release report** – For READY rows, generate release report
5. **Manual code review** – Complete checklist, commit, promote

## UI Integration

On the Mapping Readiness page, for rows with status READY:

- **Generate Release Report** – Fetches full report (readyForPromotion, blockers, evidence, checklist)
- **Generate Markdown** – Fetches markdown artifact for sharing or documentation

The report is displayed in a panel; no Apply or Promote button. This is review-only.
