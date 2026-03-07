# Canonical Mapping Engine

The Canonical Mapping Engine provides deterministic field/path-based transforms between canonical and vendor payloads. It is preview and validation only—no runtime execution, no external calls.

## Overview

- **Canonical model** is the source of truth for operation schemas.
- **Mappings** are vendor adapters that transform payloads in both directions.
- **Deterministic only** in this phase—no LLM-generated mapping logic.
- **Preview/validation** behavior—no execution is performed.

## Supported Mapping Primitives

- **Direct field copy**: `"vendorField": "$.canonicalField"`
- **Nested path extraction**: `"nested.out": "$.a.b.c"`
- **Constants**: `"fixedValue": "literal"` (non-`$.` values)
- **Missing field**: yields a clear validation warning/violation

## API Endpoints

### GET /v1/mappings/canonical/operations

Lists operations that have mapping definitions available. Returns `items` with `operationCode`, `version`, `title`, `description`, and `vendorPairs`.

### POST /v1/mappings/canonical/preview

Preview a transform without execution.

**Request body:**
```json
{
  "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
  "version": "1.0",
  "sourceVendor": "LH001",
  "targetVendor": "LH002",
  "direction": "CANONICAL_TO_VENDOR",
  "inputPayload": {
    "memberIdWithPrefix": "LH001-12345",
    "date": "2025-03-06"
  }
}
```

**Response:** `valid`, `operationCode`, `version`, `sourceVendor`, `targetVendor`, `direction`, `mappingDefinitionSummary`, `inputPayload`, `outputPayload`, `errors`, `notes`.

### POST /v1/mappings/canonical/validate

Validate mapping availability and payload transformability. Returns `valid`, `mappingAvailable`, `warnings`, `notes`.

## Vendor-Pair Mappings (Code-First)

First-pass mappings are defined in code under `apps/api/src/schema/canonical_mappings/`:

| Operation | Version | Vendor Pair | File |
|-----------|---------|-------------|------|
| GET_VERIFY_MEMBER_ELIGIBILITY | 1.0 | LH001 → LH002 | eligibility_v1_lh001_lh002.py |
| GET_MEMBER_ACCUMULATORS | 1.0 | LH001 → LH002 | member_accumulators_v1_lh001_lh002.py |

## Relationship to Runtime

- The mapping engine does **not** replace the existing runtime mapping logic.
- It provides a deterministic preview surface for modeling and validation.
- Future integration: runtime could consume these definitions or align with them.

## Future Path

- Runtime integration: wire mapping definitions into the execute path.
- AI-assisted mapping suggestions: LLM could propose mappings for review.
- Persistence: move from code-first to DB-backed definitions if needed.
