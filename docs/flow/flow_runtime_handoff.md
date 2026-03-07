# Flow Runtime Handoff

Flow Runtime Handoff generates a canonical execution package from a validated flow draft. It bridges the Flow Builder (authoring surface) and the existing Runtime (preflight/execute path) without introducing a new runtime engine or performing execution.

## Overview

- **Flow draft validation** remains the source of truth for flow structure.
- **Handoff generation** produces a deterministic canonical execution package suitable for preflight and execute.
- **No execution** is performed by handoff generation. It is a packaging step only.
- **Optional preflight** can be run as part of handoff to validate runtime readiness before any execute call.

## Canonical Execution Package Shape

The handoff returns a `canonicalExecutionPackage` with:

```json
{
  "sourceVendor": "LH001",
  "targetVendor": "LH002",
  "envelope": {
    "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
    "version": "1.0",
    "direction": "REQUEST",
    "correlationId": "corr-flow-...",
    "timestamp": "2025-03-06T12:00:00Z",
    "context": {},
    "payload": { "memberIdWithPrefix": "LH001-12345", "date": "2025-03-06" }
  }
}
```

This shape matches the input expected by:

- `POST /v1/runtime/canonical/preflight`
- `POST /v1/runtime/canonical/execute` (bridge mode)

## Relationship to Existing Paths

| Step | Endpoint | Behavior |
|------|----------|----------|
| Validate draft | `POST /v1/flow/draft/validate` | Validates flow structure, resolves version aliases |
| Generate handoff | `POST /v1/flow/runtime/handoff` | Builds canonical execution package from draft |
| Generate + preflight | `POST /v1/flow/runtime/handoff/preflight` | Same as handoff, plus runs canonical preflight |
| Preflight (standalone) | `POST /v1/runtime/canonical/preflight` | Validates envelope, allowlist, mapping |
| Execute | `POST /v1/runtime/canonical/execute` | Runs preflight then execute via existing runtime |

Handoff does **not** call execute. It only produces the package. The admin or partner can then use that package with the existing preflight/execute endpoints.

## Payload Resolution

- If the request includes an explicit `payload` object (non-empty), it is used as the canonical request payload.
- If `payload` is absent or empty, the handoff service uses the canonical operation's example request from the registry.
- This allows Flow Builder to prefill from examples and optionally let the user edit before generating the handoff.

## API Endpoints

### POST /v1/flow/runtime/handoff

Builds the canonical execution package. No preflight.

**Request body:**
```json
{
  "draft": {
    "name": "Eligibility Check Flow",
    "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
    "version": "1.0",
    "sourceVendor": "LH001",
    "targetVendor": "LH002",
    "trigger": { "type": "MANUAL" },
    "mappingMode": "CANONICAL_FIRST",
    "notes": "optional"
  },
  "payload": { "memberIdWithPrefix": "LH001-12345", "date": "2025-03-06" },
  "context": {},
  "runPreflight": false
}
```

### POST /v1/flow/runtime/handoff/preflight

Same request shape. Builds handoff and runs canonical preflight. Response includes `preflight` with checks and execution plan.

**Note:** `runPreflight` in the body is ignored for these endpoints; the route determines behavior (`/handoff` = no preflight, `/handoff/preflight` = with preflight).

## Admin-Only

Both endpoints require admin JWT and `REGISTRY_READ` policy. No vendor or runtime tokens.

## Future: Persisted Orchestration

Handoff is intentionally stateless and non-persistent. A future enhancement could:

- Persist handoff packages for reuse
- Link flow drafts to execution history
- Support scheduled or event-driven execution

The current design keeps the handoff as a deterministic, read-only packaging step to avoid coupling to orchestration concerns.
