# Integration Hub – Security Documentation

Security design and implementation docs for the 2 REST endpoints (`/v1/execute`, `/v1/ai/execute`).

## Documents

| Document | Purpose |
|----------|---------|
| [01-final-architecture.md](./01-final-architecture.md) | Final architecture and auth model |
| [02-documentation.md](./02-documentation.md) | API and integration documentation |
| [03-dev-plan.md](./03-dev-plan.md) | Development plan and sequencing |
| [04-dev-setup-guide.md](./04-dev-setup-guide.md) | Dev environment setup guide |
| [05-checklist.md](./05-checklist.md) | Validation and deployment checklist |
| [06-phases-and-test-plan.md](./06-phases-and-test-plan.md) | Phase-by-phase implementation with test plan |
| [07-oauth-migration-agent-instruction.md](./07-oauth-migration-agent-instruction.md) | OAuth/Auth0 migration agent instruction |
| [08-auth-profile-security-diagnostics-helpers.md](./08-auth-profile-security-diagnostics-helpers.md) | Security and diagnostics helper rationale for auth profile testing |
| [CURSOR_EXECUTE.md](./CURSOR_EXECUTE.md) | Cursor execution instructions (confirmation required) |

## Quick reference

- **Endpoints**: POST `/v1/execute`, POST `/v1/ai/execute`
- **Auth**: JWT, mTLS, per-consumer API keys
- **Local dev**: Auth bypass when `AUTH_BYPASS=true`
