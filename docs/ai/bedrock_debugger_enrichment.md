# Bedrock Debugger Enrichment

Optional AI summarization and remediation on top of the deterministic AI Debugger.

## Design Principles

- **Deterministic debugger remains authoritative** – Status, summary, and findings are never overridden by AI.
- **Bedrock enhancement is optional and advisory** – Off by default; enabled only when requested and configured.
- **Bedrock calls stay inside AI Gateway** – No `bedrock:InvokeModel` on registry or vendor-registry lambdas.
- **Internal invoke only** – Registry/vendor-registry use `lambda:InvokeFunction` to call the AI Gateway Lambda; no new public AI API surface.

## Architecture

```
User (admin/partner UI)
    │
    ▼
registry_lambda / vendor_registry_lambda
    │  1. Build deterministic report
    │  2. If enhanceWithAi=true and config allows:
    │     → lambda.invoke(ai_gateway_lambda, { action: "debugger_enrich", report: redacted })
    ▼
ai_gateway_lambda (has Bedrock IAM)
    │  3. Handle event.action == "debugger_enrich"
    │  4. Run bedrock_debugger_enricher (redact, call Bedrock)
    │  5. Return enrichment object
    ▼
registry_lambda / vendor_registry_lambda
    │  6. Merge enrichment into report (additive only)
    ▼
User receives deterministic report + optional aiSummary, remediationPlan, etc.
```

## PHI-Safe / Redaction Strategy

- **No raw payload bodies** sent to Bedrock. `normalizedArtifacts` (payload, draft, sandboxResult) are excluded from the prompt.
- **Sanitized findings** – Finding messages are sanitized to remove quoted strings, SSN-like patterns, memberId-like values.
- **Safe metadata only** – debugType, status, summary, operationCode, version, sanitized findings, notes.

## Fallback Behavior

When Bedrock is disabled, unavailable, times out, or errors:

- Deterministic report is returned unchanged.
- `aiWarnings` includes "AI enhancement unavailable; deterministic debugger result returned."
- `modelInfo.enhanced` = false, `modelInfo.reason` = reason code.

## Configuration

| Env Var | Purpose | Default |
|---------|---------|---------|
| BEDROCK_DEBUGGER_ENABLED | Enable debugger enrichment | false |
| BEDROCK_DEBUGGER_MODEL_ID | Bedrock model for enrichment | (formatter model) |
| BEDROCK_DEBUGGER_TIMEOUT_MS | Timeout for Bedrock call | 8000 |
| BEDROCK_DEBUGGER_ALLOW_LOCAL | Allow Bedrock in local/dev | false |
| AI_GATEWAY_FUNCTION_ARN | AI Gateway Lambda ARN (registry/vendor) | (from CDK) |

## Endpoints Extended

- `POST /v1/ai/debug/request/analyze` – accepts `enhanceWithAi: true`
- `POST /v1/ai/debug/flow-draft/analyze` – accepts `enhanceWithAi: true`
- `POST /v1/ai/debug/sandbox-result/analyze` – accepts `enhanceWithAi: true`
- Partner equivalents under `/v1/vendor/syntegris/ai/debug/*`

No new public routes. Additive request/response fields only.
