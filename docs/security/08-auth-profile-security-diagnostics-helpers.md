# Auth Profile Security & Diagnostics Helpers

## Purpose

This document explains the **supporting security/diagnostics helpers** used by Admin auth-profile tools:

- `POST /v1/registry/auth-profiles/test-connection`
- `POST /v1/registry/auth-profiles/token-preview`
- `POST /v1/registry/auth-profiles/mtls-validate`

The goal is to make troubleshooting possible **without exposing secrets** and without weakening runtime security.

## Why these helpers exist

Auth profile setup often fails for reasons that are hard to see from UI-only validation:

- wrong auth field names
- invalid credentials format
- token endpoint misconfiguration
- TLS/certificate mismatch
- DNS/network reachability problems

These helpers provide safe, bounded diagnostics so admins can fix configuration quickly while preserving security controls.

## Security principles

All helper behavior follows these principles:

1. **No secret persistence**
   - Test credentials and preview tokens are not written to DB.
   - Test request/response payloads are not persisted.

2. **No secret leakage**
   - Authorization/API key/password/private-key values are redacted before returning diagnostics.
   - Responses include only safe metadata and bounded previews.

3. **Bounded execution**
   - Hard timeout cap (<= 10s).
   - Response preview truncated (<= 2048 chars).

4. **Network safety (SSRF guard)**
   - HTTPS-only by default.
   - DNS resolution + private/local/link-local range blocking.
   - Dev-only bypass via `ALLOW_SSRF_DEV=true` for local testing.

5. **Admin-only access**
   - Endpoints are protected by existing admin JWT/role guard (`admin_guard` + `bcpAuth` path).

## Supporting helpers and rationale

### 1) Auth type normalization

Helpers normalize legacy aliases (for example `STATIC_BEARER` / `BEARER_TOKEN`) into canonical runtime types.

**Reason:** avoids inconsistent behavior between old UI payloads and new endpoint logic.

### 2) Timeout normalization

`timeoutMs` is clamped to a safe max.

**Reason:** prevents long-running probes and resource abuse.

### 3) Central redaction helpers

Redaction is handled centrally for:

- `Authorization` headers
- API key headers/query values
- secret-like header names (`token`, `secret`, `key`, `password`)

**Reason:** ensures no endpoint accidentally returns plaintext secrets in debug output.

### 4) Response/body preview bounding

Response snippets are normalized and truncated to 2 KB.

**Reason:** avoids leaking full payloads and prevents oversized diagnostics responses.

### 5) SSRF target validation helpers

Validation checks:

- scheme (HTTPS required unless dev override)
- hostname resolution
- blocked ranges (localhost, RFC1918, link-local, reserved/private)

**Reason:** prevents internal-network probing through diagnostic endpoints.

### 6) JWT preview token helper + cache diagnostics

Token preview uses client-credentials flow and returns:

- redacted token
- token length
- `expires_in`
- decoded JWT metadata (if token is JWT)
- cache metadata (`cacheKeyHash`, `expiresAt`, `lastFetchedAt`)

**Reason:** provides actionable diagnostics (claims/expiry/cache timing) without exposing full token material.

### 7) mTLS certificate validation helpers

Validator checks:

- certificate PEM parse
- private key PEM parse
- cert/key public key match
- expiration and expiring-soon warning (<30 days)
- subject/issuer/SAN metadata
- optional CA bundle parse warning

**Reason:** catches high-impact certificate mistakes before production traffic fails.

## Diagnostic categories

Error categories are normalized so UI can show meaningful feedback:

- `BLOCKED` (SSRF policy)
- `DNS`
- `TIMEOUT`
- `TLS`
- `AUTH`
- `UPSTREAM`
- `UNKNOWN`

**Reason:** consistent categories improve operator response and reduce guesswork.

## Operational guidance

- Keep `ALLOW_SSRF_DEV` unset/false outside local development.
- Never add logging that prints `authConfig` raw values.
- Treat diagnostics endpoints as troubleshooting tools, not runtime traffic paths.
- Continue using runtime execution path for true end-to-end business validation.

## Summary

These helpers intentionally balance two needs:

- **Security posture** (redaction, SSRF controls, bounded execution, admin guard)
- **Operator usability** (clear diagnostics for auth, token, TLS, and connectivity issues)

This is why they exist: to reduce misconfiguration risk while preserving strict secret-handling and network safety standards.
