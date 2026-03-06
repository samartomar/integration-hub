# Ephemeral config

Developer-specific config overrides for local dev. Not committed.

## Format

Create \{developer}.json\ (e.g. \lice.json\) with env overrides:
\\\json
{
  \"customDomainRoot\": \"\",
  \"environment\": \"dev\"
}
\\\

These overlay \packages/env-config/env-config.json\ when present.
