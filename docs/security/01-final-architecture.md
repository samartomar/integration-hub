# Final Architecture – 2 REST Endpoints

## Endpoints

- **POST** `/v1/execute` – Integration execution (Routing Lambda)
- **POST** `/v1/ai/execute` – AI/Bedrock (PROMPT & DATA) (AI Gateway Lambda)

## Auth model (four paths)

| Caller type | Mechanism |
|-------------|------------|
| Admin/Vendor UI | Auth0 JWT |
| Servers / Bots / M2M | Auth0 client credentials → JWT |
| Per-consumer | DB-backed API keys (hashed) |
| Apache registrar | mTLS client certificate |

## Per-consumer API keys

- Hash only (SHA-256 + salt); no plaintext storage
- Salt from Secrets Manager
- One key per consumer; revocable; optional scopes/rotation

## Infrastructure

- Input validation: strict schema
- PII: in-house handling
- SSRF, WAF, Shield: in place in prod
- Error handling: canonical only, no internals
- Audit logging: consumer identity in all logs
- Replay: idempotency; optional timestamp
- Request signing: optional enhancement

## Bedrock & AI

- PII: limit/mask in prompts
- Prompt injection: sanitize/constrain
- Model output: treat as untrusted; validate
- Cost control: limits and monitoring
