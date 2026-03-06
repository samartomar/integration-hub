# Partner App Provisioning Feature

## Overview

Automate creation of OAuth 2.0 applications (client_id + client_secret) for each partner during onboarding. Partners use these credentials to obtain JWTs and call the Integration Hub APIs (Execute, AI Gateway, Vendor API).

## Supported Identity Providers

| Provider | Status | Design | UI Spec | Implementation |
|----------|--------|--------|---------|----------------|
| **Okta** | Target (final delivery) | [01-okta-design.md](./01-okta-design.md) | [02-okta-ui-spec.md](./02-okta-ui-spec.md) | N/A (configure Okta directly) |
| **Auth0** | Current (POC) | Same concepts | Same UI | [03-auth0-implementation.md](./03-auth0-implementation.md) |

## Documents

1. **[01-okta-design.md](./01-okta-design.md)** – Okta architecture, API, and configuration
2. **[02-okta-ui-spec.md](./02-okta-ui-spec.md)** – UI specification for partner app provisioning
3. **[03-auth0-implementation.md](./03-auth0-implementation.md)** – Agent implementation guide for Auth0 (current POC)

## Flow Summary

```
Partner onboarded (vendor_code created in control_plane.vendors)
         │
         ▼
Provision OAuth app in IdP (Okta or Auth0)
  - Create M2M / Service Application
  - Configure vendor claim (lhcode) in token
  - Generate client_id, client_secret
         │
         ▼
Store app reference in Hub (optional table: partner_oauth_apps)
         │
         ▼
Deliver credentials to partner (secure channel)
         │
         ▼
Partner uses client credentials → JWT → API calls
```

## References

- [02-auth-identity.mdc](../../.cursor/rules/02-auth-identity.mdc) – JWT-only, vendor from claims
- [07-oauth-migration-agent-instruction.md](../../security/07-oauth-migration-agent-instruction.md) – Current Auth0 config
