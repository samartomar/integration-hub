# Environment Config (Single Source of Truth)

## Files

| File | Purpose |
|------|---------|
| `env-config.json` | Base config (dev defaults) |
| `env-config.prod.json` | Prod overrides (optional) |

**Load order:** Base → `env-config.{environment}.json` (if exists) → env vars → CDK context.

## Base: `env-config.json`

```json
{
  "environment": "dev",
  "customDomainRoot": "",
  "customDomainHostedZoneId": ""
}
```

## Prod: `env-config.prod.json`

When `ENVIRONMENT=prod` (e.g. prod buildspec sets it), the loader also reads this file and overlays on base. Use it for prod-specific values (e.g. prod hosted zone ID if different from dev).

```json
{
  "environment": "prod",
  "customDomainRoot": "gosam.info",
  "customDomainHostedZoneId": "Z0123456789ABC"
}
```

| Key | Description |
|-----|-------------|
| `environment` | `dev` or `prod` |
| `customDomainRoot` | Root domain. Empty = AWS URLs only |
| `customDomainHostedZoneId` | Route53 zone ID (optional; use lookup if empty) |

## Who Reads It

- **CDK** (`app.py`) – loads on synth/deploy
- **Buildspecs** – `tooling/scripts/load_env_config.py`; prod buildspec sets `ENVIRONMENT=prod` so `env-config.prod.json` is used
- **Frontend builds** – `eval $(python tooling/scripts/load_env_config.py -v)`

## Overrides

Env vars and CDK `-c` flags override file values.
