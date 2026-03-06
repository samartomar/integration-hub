# Runtime Flow (Execute Pipeline)

The execute pipeline is the heart of the Integration Hub. Every request goes through these 11 steps in order.

---

## Pipeline Steps

| Step | Action | Failure Mode |
|------|--------|---------------|
| **1** | Auth validated at API Gateway | 401 if invalid JWT/API key |
| **2** | Allowlist check | `ACCESS_DENIED` if blocked |
| **3** | Load effective contract | `CONTRACT_NOT_FOUND` if neither vendor nor canonical exists |
| **4** | Validate payload | `SCHEMA_VALIDATION_FAILED` if invalid |
| **5** | Load effective mapping | `MAPPING_NOT_FOUND` only when mapping is required |
| **6** | Apply mapping | `MAPPING_FAILED` if transform fails |
| **7** | Load effective endpoint | `ENDPOINT_NOT_FOUND` if no active endpoint |
| **8** | Make downstream call | Timeout, connection, or HTTP error |
| **9** | Validate response (optional) | `DOWNSTREAM_INVALID_RESPONSE` |
| **10** | Apply response mapping | `MAPPING_FAILED` |
| **11** | Return final canonical response | — |

---

## Invariants

1. **Direction** – Derived once, passed consistently through the pipeline.
2. **includeActuals** – Always included when `includeActuals=true`.
3. **Errors** – Must include canonical error model (code, message, details).
4. **Audit** – Every execute is recorded in `data_plane.transactions`.

---

## Error Response Format

All errors use a canonical envelope. HTTP status may be 400, 401, 403, 404, 502, etc., depending on the error code.

**Structure:**

```json
{
  "transactionId": "uuid",
  "correlationId": "uuid",
  "error": {
    "code": "ALLOWLIST_DENIED",
    "message": "Access denied: source LH001 not allowed to call target LH002 for GET_RECEIPT",
    "category": "POLICY",
    "retryable": false,
    "details": {}
  }
}
```

| Field | Description |
|-------|-------------|
| `transactionId` | Unique ID for the transaction (may be empty on early failures) |
| `correlationId` | Request correlation ID |
| `error.code` | Canonical code (e.g. `AUTH_ERROR`, `VENDOR_NOT_FOUND`, `ENDPOINT_NOT_FOUND`) |
| `error.message` | Human-readable message |
| `error.category` | `VALIDATION`, `POLICY`, `MAPPING`, `DOWNSTREAM`, `PLATFORM`, `AUTH`, `NOT_FOUND`, `CONFLICT`, `RATE_LIMIT` |
| `error.retryable` | Whether the client may retry |
| `error.details` | Optional extra info (e.g. `violations`, `requestBodyRaw`, `downstreamStatus`) |

---

## Request Flow (Simplified)

```
Client
  │
  ▼
API Gateway (auth: JWT)
  │
  ▼
Routing Lambda
  │
  ├─► Parse body (sourceVendor, targetVendor, operation, value)
  ├─► Resolve source vendor (JWT claim or API key lookup)
  ├─► Derive flow direction (OUTBOUND: source→target)
  ├─► Allowlist check
  ├─► load_effective_contract(flow_direction)
  ├─► Validate payload vs effective contract
  ├─► resolve_effective_mapping(flow_direction)
  ├─► Apply request mapping (canonical → vendor format)
  ├─► load_effective_endpoint(operation, vendor, flow_direction)
  ├─► HTTP call to downstream
  ├─► Apply response mapping (vendor → canonical format)
  ├─► Record transaction
  │
  ▼
Response (canonical form)
```

---

## Two Entry Points

| Path | Auth | Source Vendor |
|-----|------|----------------|
| `/v1/integrations/execute` | JWT (Authorization: Bearer) | From JWT (never from body) |
| `/v1/execute` (Runtime API) | JWT (Authorization: Bearer) | From body `sourceVendor` (required) |

---

## Redrive

Admin can redrive a failed transaction via `POST /v1/admin/redrive/{transactionId}`. Uses the original request payload; skips idempotency if explicitly requested.

---

## Key Code

- **Main handler:** `apps/api/src/lambda/routing_lambda.py`
- **Contract utils:** `apps/api/src/lambda/contract_utils.py`
- **Endpoint utils:** `apps/api/src/lambda/endpoint_utils.py`
- **Mapping:** `apps/api/src/lambda/routing/transform.py`
- **Canonical errors:** `apps/api/src/lambda/canonical_error.py`

---

Next: [06_LOCAL_DEV.md](06_LOCAL_DEV.md)
