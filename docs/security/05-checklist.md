# Security Validation Checklist

## Auth

- [ ] JWT: valid token accepted
- [ ] JWT: invalid/expired rejected (401)
- [ ] API key: valid key accepted
- [ ] API key: revoked key rejected (401)
- [ ] mTLS: valid cert accepted (when enabled)
- [ ] Bypass: works only when AUTH_BYPASS=true

## Input validation

- [ ] Missing required → 400
- [ ] Invalid types → 400
- [ ] Oversized body → 400/413
- [ ] Non-JSON → 400

## Error handling

- [ ] No stack traces in responses
- [ ] No file paths or hostnames
- [ ] Canonical error structure used

## Audit

- [ ] Consumer identity in transaction/audit logs
- [ ] Auth failures logged

## Replay

- [ ] Idempotency works (same key = same result, no duplicate work)

## Request signing (if implemented)

- [ ] Valid signature accepted
- [ ] Tampered body rejected
- [ ] Old timestamp rejected
