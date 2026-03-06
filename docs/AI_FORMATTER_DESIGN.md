# AI Formatter Design

## Scope

This document defines AI formatter behavior for `POST /v1/ai/execute` across `DATA` and `PROMPT` request types.

## Decision model

Formatter decisions are deterministic and must run in this exact order:

1. Global/vendor feature gate (`ai_formatter_enabled`)
2. Operation mode (`control_plane.operations.ai_presentation_mode`)
3. Request flag (`aiFormatter`)
4. Formatter call (Bedrock or local stub)

### Gate fallback precedence

1. `feature_code='ai_formatter_enabled' AND vendor_code=<vendor_code from bcpAuth>`
2. else `feature_code='ai_formatter_enabled' AND vendor_code IS NULL`
3. else disabled (`false`)

If no row exists at either level, formatter is off.

## Identity source

- Caller identity is derived from JWT `bcpAuth`.
- The resolved vendor string is used for gate lookup (`feature_gates.vendor_code`).
- Request body vendor fields are never trusted as identity source.

## Operation modes

Supported values:

- `RAW_ONLY`
- `RAW_AND_FORMATTED`

Fallback behavior:

- `NULL` mode => `RAW_ONLY`
- Unknown/legacy mode => `RAW_ONLY`

## Request contract

For DATA:

- `aiFormatter` supports boolean only (`true`/`false`)
- missing `aiFormatter` defaults to `false`
- object forms are rejected as validation errors

For PROMPT:

- `aiFormatter` input is ignored

## Reasons enum

- `FEATURE_DISABLED`
- `MODE_RAW_ONLY`
- `REQUEST_DISABLED`
- `FORMATTER_ERROR`
- `APPLIED`
- `PROMPT_MODE`

## Response envelope

The AI endpoint always returns:

- `requestType`
- `rawResult`
- `aiFormatter`:
  - `applied`
  - `mode`
  - `model`
  - `reason`
  - `formattedText`
- `finalText`
- `error`

### DATA behavior

- Formatter runs only when gate allows, mode is `RAW_AND_FORMATTED`, and `aiFormatter=true`.
- If formatter is not applied, `finalText` is `null`.
- If formatter is applied, `finalText` equals `aiFormatter.formattedText`.

### PROMPT behavior

- Prompt/agent execution remains unchanged.
- `aiFormatter` always describes "formatter not used":
  - `applied=false`
  - `reason='PROMPT_MODE'`
  - `mode=null`
  - `model=null`
  - `formattedText=null`
- `finalText` contains the prompt agent output when available.

## Formatter input source

For DATA formatting input:

1. use `rawResult.responseBody` when present
2. otherwise use full `rawResult`

Input is truncated using `AI_FORMATTER_MAX_PROMPT_CHARS`.

## Runtime modes

- `USE_BEDROCK=false`: local deterministic stub summary is returned.
- `USE_BEDROCK=true`: Bedrock formatter is called.
- Output is truncated by `AI_FORMATTER_MAX_OUTPUT_CHARS`.

On formatter exceptions/timeouts:

- set `reason='FORMATTER_ERROR'`
- keep `rawResult` unchanged
- keep execute result semantics unchanged
