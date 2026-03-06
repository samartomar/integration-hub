# Platform Invariants

This document lists the invariants enforced by the platform invariant test suite and maps each to its test file.

## Run command

```bash
python -m pytest tests/platform_invariants -q
```

---

## Invariant-to-test mapping

| # | Invariant | Test file |
|---|-----------|-----------|
| 1 | Runtime blocks vendor spoof when token vendor != request vendor | `test_identity_invariants.py` |
| 2 | Vendor-scoped route fails if `bcpAuth` is missing | `test_identity_invariants.py` |
| 3 | `routing_lambda` enforces policy | `test_policy_invariants.py` |
| 4 | `vendor_registry_lambda` enforces policy | `test_policy_invariants.py` |
| 5 | `onboarding_lambda` enforces policy | `test_policy_invariants.py` |
| 6 | Protected routes use canonical error responses | `test_response_invariants.py` |
| 7 | `ai_gateway_lambda` uses custom AI envelope (documented exception) | `test_response_invariants.py` |
| 8 | `expandSensitive` requires PHI-approved group | `test_security_invariants.py` |
| 9 | Mission Control activity/topology endpoints return metadata only | `test_security_invariants.py` |
| 10 | Vendor routes expected by UI exist | `test_route_contract_invariants.py` |
| 11 | Admin mission control routes are protected by admin auth/group | `test_route_contract_invariants.py` |

---

## Documented exceptions

- **AI Gateway custom envelope**: `ai_gateway_lambda` intentionally uses an AI-specific response envelope (`requestType`, `rawResult`, `aiFormatter`, `finalText`, `error`) for DATA and PROMPT modes. This is a documented exception to the canonical response contract. See `docs/platform/platform_contract.md` §4.

---

## Identity invariants

- Vendor identity must come only from JWT claim `bcpAuth`
- Request body/query/header must not override vendor identity
- Vendor mismatch must be denied with `VENDOR_SPOOF_BLOCKED`

## Policy invariants

- Protected lambdas must evaluate centralized policy before business logic

## Response invariants

- Protected APIs must return canonical responses
- Ad hoc error envelopes are not allowed on protected routes
- Documented exceptions are allowed only if intentional

## Security invariants

- PHI is redacted by default
- `expandSensitive` requires approved group
- Admin routes require admin auth/group
- Observability endpoints return metadata only

## Route contract invariants

- Vendor UI expected backend routes must exist
- Admin-only routes must remain protected
- Vendor routes must not expose cross-vendor behavior
