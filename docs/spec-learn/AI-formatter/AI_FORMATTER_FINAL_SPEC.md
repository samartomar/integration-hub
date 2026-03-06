# AI Formatter Final Spec

Status: approved decisions captured for implementation.

## 1) Goals and Invariants

- Admin controls AI formatting globally and per operation.
- Vendor callers can request formatter behavior, but cannot bypass admin decisions.
- AI is enhancement-only; execute truth outcome remains authoritative.

Non-negotiables:

1. Decision order is fixed: `GLOBAL_GATE -> OP_MODE -> REQUEST_FLAG -> FORMATTER_CALL`.
2. Source vendor is derived from JWT for external requests.
3. Disabling AI does not alter baseline raw DATA behavior.
4. Formatter failures never break execute outcome; they only affect `aiFormatter` metadata.

## 2) Data Model and Keys

- Use existing fields only:
  - `control_plane.operations.ai_presentation_mode`
  - `control_plane.operations.ai_formatter_prompt`
  - `control_plane.operations.ai_formatter_model`
  - `control_plane.feature_gates`
- Global gate key: `ai_formatter_enabled` (lowercase), `vendor_code = NULL`.

Supported operation values moving forward:
- `RAW_ONLY`
- `RAW_AND_FORMATTED`

`FORMAT_ONLY` is deprecated and must not be written by UI/API.

## 3) `/v1/ai/execute` Decision Behavior

Applies fixed precedence for DATA and PROMPT:

1. Global gate (`ai_formatter_enabled`)
2. Operation mode
3. Request flag (`aiFormatter`)
4. Formatter invocation

### DATA

- If gate is disabled:
  - Return normal raw execute result.
  - `aiFormatter.reason = "FEATURE_DISABLED"`, `applied = false`.
- If mode resolves to `RAW_ONLY`:
  - `reason = "MODE_RAW_ONLY"`, `applied = false`.
- If request flag disables:
  - `reason = "REQUEST_DISABLED"`, `applied = false`.
- If formatter fails/timeout/config issue:
  - `reason = "FORMATTER_ERROR"`, `applied = false`.
- On formatter success:
  - `reason = "APPLIED"`, `applied = true`, `formattedText` set.

### PROMPT

Global gate also applies.

- If disabled:
  - No Bedrock call.
  - Return `error.code = "AI_DISABLED"`.
  - `aiFormatter.reason = "FEATURE_DISABLED"`.

## 4) `aiFormatter` Response Contract

Every `/v1/ai/execute` response includes:

```json
{
  "aiFormatter": {
    "applied": false,
    "mode": "RAW_ONLY",
    "model": "string-or-null",
    "reason": "FEATURE_DISABLED",
    "formattedText": null
  }
}
```

Mode semantics:

- If operation has configured AI mode, `aiFormatter.mode` reflects that mode even when formatter is not applied.
- If operation AI mode is NULL, `aiFormatter.mode = null`.

`applied` + `reason` indicates whether formatting actually ran.

## 5) Source Vendor Safety

- JWT external requests:
  - derive source vendor from JWT claim only.
  - ignore body `sourceVendor` / `sourceVendorCode` for DATA.
- Body/JWT mismatch must emit compact conflict log event:
  - `ai_gateway_source_vendor_conflict`
  - includes `jwtVendor`, `bodyVendor`, `operationCode`, `targetVendorCode`, `requestType`.

## 6) Registry Namespace APIs (No New Admin Namespace)

Global settings:
- `GET /v1/registry/ai/settings`
- `PUT /v1/registry/ai/settings`

Operation settings:
- `GET /v1/registry/operations/{operationCode}/ai-settings`
- `PUT /v1/registry/operations/{operationCode}/ai-settings`

Formatter test:
- `POST /v1/registry/ai/test`

## 7) Outcome Guardrail

AI metadata is decoration.

For DATA, response payload/status/error from execute remains the same as non-AI path; only `aiFormatter` fields change based on formatter decision/outcome.

