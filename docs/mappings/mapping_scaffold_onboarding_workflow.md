# Mapping Scaffold Onboarding Workflow

## Overview

The Mapping Scaffold Generator produces **code-first scaffold bundles** for onboarding new operation/vendor-pair mappings. It is the next step after [Certification](mapping_certification_workflow.md) for new vendor pairs or operations. **Artifact-only.** No persistence. No runtime mutation. No automatic apply.

## Where Scaffold Fits

Recommended onboarding flow for new vendor pairs or operations:

1. **Generate Scaffold** – Produce mapping definition stub, fixture stub, test stub, and markdown
2. **Fill mapping definition** – Implement field mappings in the generated stub
3. **Add fixtures** – Add fixture cases to the fixture stub
4. **Certify** – Run fixture-based certification
5. **Promotion artifact** (if needed) – Generate promotion markdown for code review
6. **Manual code review/update** – Apply changes to `canonical_mappings/` and fixtures

Scaffold can be generated **without** an existing mapping definition. It is intended for **new** operation/vendor-pair combinations.

## Design Principles

1. **Deterministic mappings remain authoritative** – runtime uses code-first definitions only
2. **Code-first mapping definitions** – scaffold produces stubs; developer fills in logic
3. **No automatic apply** – scaffold never writes files or mutates runtime mappings
4. **Artifact-only** – generates stubs and markdown for review/copy-paste
5. **Admin-only** in this phase
6. **Reuses canonical registry** – validates operation/version via `resolve_version`

## How It Works

1. **Input** – Operation code, version, source vendor, target vendor, directions
2. **Validation** – Operation must be supported; version must exist in canonical registry
3. **Output** – Scaffold bundle containing:
   - **File paths** – mapping definition, fixture, test file paths
   - **Mapping definition stub** – Python module skeleton
   - **Fixture stub** – Fixture module skeleton
   - **Test stub** – Certification test skeleton
   - **Review checklist** – Onboarding guidance
   - **Markdown** – Onboarding artifact for documentation

4. **Supported operations** – GET_VERIFY_MEMBER_ELIGIBILITY, GET_MEMBER_ACCUMULATORS (extensible)

## API Endpoints

- **POST /v1/mappings/canonical/scaffold-bundle** – Generate full scaffold bundle (stubs + markdown)
- **POST /v1/mappings/canonical/scaffold-bundle/markdown** – Generate markdown only

Scaffold payload:

```json
{
  "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
  "version": "1.0",
  "sourceVendor": "LH001",
  "targetVendor": "LH002",
  "directions": ["CANONICAL_TO_VENDOR", "VENDOR_TO_CANONICAL"]
}
```

## File Path Conventions

Paths are inferred from operation, version, and vendor pair:

- **Mapping definition**: `apps/api/src/schema/canonical_mappings/{prefix}_v{major}_{source}_{target}.py`
- **Fixture**: `apps/api/src/schema/mapping_fixtures/{prefix}_v{major}_{source}_{target}.py`
- **Test**: `tests/schema/test_mapping_certification_{prefix}_v{major}_{source}_{target}.py`

Example for GET_VERIFY_MEMBER_ELIGIBILITY v1.0 LH001→LH002:

- `eligibility_v1_lh001_lh002.py` (definition, fixture, test)

## Related

- [Mapping Certification Workflow](mapping_certification_workflow.md)
- [Mapping Promotion Artifact Workflow](mapping_promotion_artifact_workflow.md)
- [Mapping Proposal Workflow](mapping_proposal_workflow.md)
- [Canonical Mapping Engine](canonical_mapping_engine.md)
