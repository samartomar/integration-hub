# Rules Guide

How to use `.cursor/rules/` while coding. These rule files guide both AI assistants and developers.

---

## What Are the Rules?

Small, focused `.mdc` files in `.cursor/rules/` that describe:

- Invariants (e.g. vendor identity from JWT only)
- Correct functions to use (e.g. `load_effective_contract`)
- Error handling (e.g. when to return `CONTRACT_NOT_FOUND`)
- Non-goals and constraints

The rules are always applied in Cursor when working in this repo.

**Naming convention:** rule folders use lowercase-kebab-case, and files are numbered per folder starting at `00-*`.

---

## Master Index: `00-index.mdc`

Use `00-index.mdc` to know **which rules apply to what**. It maps areas of the codebase to the relevant rule files.

---

## When Changing Auth or Vendor Identity

Open:

- `.cursor/rules/security-identity/00-auth-federation.mdc` – JWT-only auth, vendor identity from claims (`vendor_code`)
- `.cursor/rules/governance/00-allowlist-access.mdc` – How source/target + operation shape access

**Don't:** Read vendor from headers, query params, or body.  
**Do:** Use JWT claims (for example `vendor_code`).

---

## When Changing Runtime Execute

Open:

- `.cursor/rules/data-model/00-contracts.mdc` – Effective contract, canonical fallback
- `.cursor/rules/data-model/01-mappings.mdc` – Effective mapping, canonical pass-through
- `.cursor/rules/data-model/02-endpoints.mdc` – Endpoint resolution, `ENDPOINT_NOT_FOUND`
- `.cursor/rules/runtime/00-execute-runtime.mdc` – The 11 pipeline steps

**Don't:** Load contracts without direction; return "Missing mapping" when canonical pass-through is valid.  
**Do:** Use `load_effective_contract(flow_direction)`, `resolve_effective_mapping`, `load_effective_endpoint`.

---

## When Changing AI Gateway

Open:

- `.cursor/rules/runtime/00-execute-runtime.mdc` – Execute pipeline
- `.cursor/rules/runtime/01-ai-gateway.mdc` – PROMPT vs DATA, Bedrock IAM, response envelope

**Don't:** Grant `bedrock:InvokeAgent` on agent (use agent-alias).  
**Do:** Return structured envelope with `rawResult`, `aiFormatter`, `finalText`, canonical error block.
**Do:** Apply AI formatter only when gate + operation mode + request flag allow it (`ai_formatter_enabled` -> `ai_presentation_mode` -> `aiFormatter`).

---

## When Changing Local Dev or Infra

Open:

- `.cursor/rules/platform/00-local-dev.mdc` – Commands, stack, invariants
- `.cursor/rules/platform/01-infra-cicd.mdc` – CDK auto-wiring, pipelines, stacks
- `.cursor/rules/platform/02-custom-domains.mdc` – Domain layout (prod vs dev)

**Don't:** Manually copy ARNs, IDs, or URLs.  
**Do:** Derive env from CDK outputs, SSM, Secrets Manager. Migrate DB before deploying lambdas.

---

## When Changing Feature Gating or Seed Data

Open:

- `.cursor/rules/product-controls/00-feature-gates.mdc` – Which edits are gated vs direct-write
- `.cursor/rules/dev-support/00-seed-data.mdc` – Seed must be deterministic, idempotent; no secrets

**Don't:** Put API keys or secrets in seed.  
**Do:** Seed canonical operations, contracts, test vendors, allowlist rules.

---

## Vision: `.cursor/rules/strategy/00-vision.mdc`

High-level business and product vision. Read when onboarding or introducing a new subsystem. Sits above all technical rules.

---

## How to Use While Coding

1. **Before editing:** Check `.cursor/rules/00-index.mdc` for relevant rules.
2. **While editing:** Keep the relevant `.mdc` files open or nearby.
3. **After editing:** Ensure your code respects the invariants (e.g. direction derived once, canonical error model).

---

## Rule File Paths

```
.cursor/rules/
├── 00-index.mdc
├── 01-master-engineering.mdc
├── context/
│   └── 00-context.mdc
├── security-identity/
│   ├── 00-auth-federation.mdc
│   └── 01-security-privacy.mdc
├── data-model/
│   ├── 00-contracts.mdc
│   ├── 01-mappings.mdc
│   └── 02-endpoints.mdc
├── governance/
│   └── 00-allowlist-access.mdc
├── runtime/
│   ├── 00-execute-runtime.mdc
│   └── 01-ai-gateway.mdc
├── platform/
│   ├── 00-local-dev.mdc
│   ├── 01-infra-cicd.mdc
│   ├── 02-custom-domains.mdc
│   ├── 03-architecture-guardrails.mdc
│   ├── 04-product-platform-model.mdc
│   └── 05-system-architecture-map.mdc
├── product-controls/
│   └── 00-feature-gates.mdc
├── dev-support/
│   └── 00-seed-data.mdc
├── agent-rules/
│   ├── 00-agent-constraints.mdc
│   ├── 01-ai-formatter.mdc
│   └── 02-git-workflow.mdc
├── repository/
│   ├── 00-branch-safety.mdc
│   ├── 01-runtime-invariants.mdc
│   └── 02-data-privacy.mdc
└── strategy/
    ├── 00-vision.mdc
    └── 01-future-roadmap.mdc
```

---

Next: [10_HANDS_ON_EXERCISES.md](10_HANDS_ON_EXERCISES.md)
