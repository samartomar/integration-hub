# Development Plan

## Sequencing

1. **Phase 1**: Lambda authorizer + Auth0 JWT
2. **Phase 2**: Per-consumer API keys (runtime API)
3. **Phase 3**: mTLS support (custom domain)
4. **Phase 4**: Request signing (optional)
5. **Phase 5**: Error handling rule + audit logging

## Dependencies

- Auth0 tenant (dev) for Phase 1
- DB migration for per-consumer keys (Phase 2)
- ACM cert + trust store for mTLS (Phase 3)

## Out of scope for initial dev

- WAF/Shield (infra-managed)
- Full Bedrock hardening (separate doc)
