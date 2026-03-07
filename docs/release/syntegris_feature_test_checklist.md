# Syntegris Feature Test Checklist

Manual and automated checks before release.

## Admin Checks

- [ ] Canonical Explorer loads operations
- [ ] Flow Builder generates handoff
- [ ] Sandbox validates request
- [ ] AI Debugger returns analysis (or stub when Bedrock disabled)
- [ ] Runtime Preflight returns mappingSummary, vendorRequestPreview
- [ ] Canonical Execute returns canonicalResponseEnvelope when EXECUTE
- [ ] Mission Control shows transactions (metadata-only)
- [ ] Mapping Readiness shows rows, release bundle works
- [ ] GET /v1/syntegris/diagnostics returns checks (no secrets)

## Partner Checks

- [ ] Partner runtime pages show mappingSummary, vendorRequestPreview, canonicalResponseEnvelope
- [ ] sourceVendor is auth-derived, non-editable
- [ ] VENDOR_SPOOF_BLOCKED on body vendor mismatch

## Runtime Checks

- [ ] Preflight passes for LH001→LH002 supported ops
- [ ] Execute (DRY_RUN) returns vendor request preview
- [ ] Execute (EXECUTE) calls runtime and returns result

## Mapping Checks

- [ ] Release bundle candidates include READY mappings
- [ ] Release bundle generation works for LH001→LH002
- [ ] Impacted files inferred correctly

## AI Debugger Checks

- [ ] Enhancement works when BEDROCK_DEBUGGER_ENABLED + MODEL_ID set
- [ ] Fallback when disabled
