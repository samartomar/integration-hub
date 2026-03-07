# Mapping Certification Workflow

## Overview

The Mapping Certification workflow is the next step after [Promotion Artifact](mapping_promotion_artifact_workflow.md). It provides **deterministic, fixture-based verification** of mapping definitions before manual code promotion. **No runtime execution.** No automatic apply. No LLM-generated authority in certification.

## Where Certification Fits

Recommended reviewer flow:

1. **Suggest** – Get deterministic baseline (optional AI suggestion)
2. **Compare** – Compare suggestion to existing mapping
3. **Proposal Package** – Generate structured proposal
4. **Promotion Artifact** – Generate code-first artifact (Python snippet, markdown)
5. **Certification** – Run fixture-based verification against current or proposed mapping
6. **Manual code update** – Apply changes to `canonical_mappings/`
7. **Rerun tests/preflight** – Validate before execute

Certification can run **without** AI suggestion or proposal package. It verifies the **current deterministic mapping definition** against known-good fixtures.

## Design Principles

1. **Deterministic mappings remain authoritative** – runtime uses code-first definitions only
2. **No automatic runtime apply** – certification never mutates mapping definitions
3. **Fixture-based and repeatable** – same fixtures produce same results
4. **No LLM-generated authority** – certification uses only deterministic engine transforms
5. **Admin-only** in this phase
6. **Reuses mapping engine** – uses existing preview/validate logic

## How It Works

1. **Fixtures** – Pre-defined test cases in `apps/api/src/schema/mapping_fixtures/`:
   - `eligibility_v1_lh001_lh002.py` – GET_VERIFY_MEMBER_ELIGIBILITY
   - `member_accumulators_v1_lh001_lh002.py` – GET_MEMBER_ACCUMULATORS

2. **Each fixture** includes:
   - `fixtureId` – unique identifier
   - `direction` – CANONICAL_TO_VENDOR or VENDOR_TO_CANONICAL
   - `inputPayload` – synthetic input
   - `expectedOutput` – expected transform result
   - `notes` – optional description

3. **Certification** – For each fixture:
   - Run `preview_mapping` with fixture input
   - Compare actual output to expected output
   - Report PASS or FAIL per fixture

4. **Summary** – Aggregated status: PASS (all pass), FAIL (any fail), WARN (e.g. candidateMapping not supported)

## API Endpoints

- **GET /v1/mappings/canonical/fixtures** – List available fixtures (optional query: operationCode, version, sourceVendor, targetVendor)
- **POST /v1/mappings/canonical/certify** – Run certification

Certify payload:

```json
{
  "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
  "version": "1.0",
  "sourceVendor": "LH001",
  "targetVendor": "LH002",
  "direction": "CANONICAL_TO_VENDOR",
  "candidateMapping": null,
  "fixtureSet": "default"
}
```

`candidateMapping` is not supported; certification uses the current deterministic mapping only.

## Fixture Sets

- **default** – LH001→LH002 for GET_VERIFY_MEMBER_ELIGIBILITY and GET_MEMBER_ACCUMULATORS
- At least one happy-path case per direction per operation
- Synthetic data only; no PHI

## Related

- [Mapping Proposal Workflow](mapping_proposal_workflow.md)
- [Mapping Promotion Artifact Workflow](mapping_promotion_artifact_workflow.md)
- [Canonical Mapping Engine](canonical_mapping_engine.md)
