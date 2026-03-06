# Integration Hub – Read This First

Welcome. This folder is your starting point for understanding the Integration Hub codebase.

## Before You Start

**Prerequisites:**

- **Python 3.11+** (see `pyproject.toml`)
- **Node.js** (LTS, for apps/web-partners)
- **Docker** (for local DB and hub-api)
- **Make** (for `make local-up`, etc.)
- **Auth0** (for vendor portal; optional for API-only dev)

**If using Cursor or an AI agent** to run dev setup commands (install, Docker, migrations, seed), review **[docs/security/CURSOR_EXECUTE.md](../security/CURSOR_EXECUTE.md)** first. Commands that modify filesystem, start services, or write to the database require explicit confirmation before execution.

---

## Document Map

| Doc | Purpose |
|-----|---------|
| **[01_OVERVIEW.md](01_OVERVIEW.md)** | What the Hub is, why it exists, and who it serves |
| **[02_GLOSSARY.md](02_GLOSSARY.md)** | Key terms: canonical, effective contract, OUTBOUND, allowlist, etc. |
| **[03_ARCHITECTURE.md](03_ARCHITECTURE.md)** | High-level architecture: planes, stacks, APIs, Lambdas |
| **[04_KEY_CONCEPTS.md](04_KEY_CONCEPTS.md)** | Contracts, mappings, endpoints, allowlist, direction semantics |
| **[05_RUNTIME_FLOW.md](05_RUNTIME_FLOW.md)** | Execute pipeline: the 11 steps from request to response |
| **[06_LOCAL_DEV.md](06_LOCAL_DEV.md)** | Run the Hub locally (Docker, make targets, Postman) |
| **[POSTMAN.md](POSTMAN.md)** | Postman collection (generate first; postman/ is gitignored) |
| **[07_FIRST_WEEK_PLAN.md](07_FIRST_WEEK_PLAN.md)** | Suggested first-week plan for new engineers |
| **[08_HOW_TO_NAVIGATE_CODEBASE.md](08_HOW_TO_NAVIGATE_CODEBASE.md)** | Where things live in the repo |
| **[09_RULES_GUIDE.md](09_RULES_GUIDE.md)** | How to use `.cursor/rules` while coding |
| **[10_HANDS_ON_EXERCISES.md](10_HANDS_ON_EXERCISES.md)** | Practical exercises to validate understanding |
| **[11_TROUBLESHOOTING.md](11_TROUBLESHOOTING.md)** | Common errors and how to fix them |
| **[DESIGN_ALIGNMENT.md](DESIGN_ALIGNMENT.md)** | DB ↔ Backend ↔ semantics alignment (design-level fixes) |

## Suggested Reading Order

1. **Day 1**: [01_OVERVIEW](01_OVERVIEW.md) → [02_GLOSSARY](02_GLOSSARY.md) → [03_ARCHITECTURE](03_ARCHITECTURE.md)
2. **Day 2**: [04_KEY_CONCEPTS](04_KEY_CONCEPTS.md) → [05_RUNTIME_FLOW](05_RUNTIME_FLOW.md) → [06_LOCAL_DEV](06_LOCAL_DEV.md)
3. **Day 3**: [08_HOW_TO_NAVIGATE_CODEBASE](08_HOW_TO_NAVIGATE_CODEBASE.md) → [09_RULES_GUIDE](09_RULES_GUIDE.md)
4. **Week 1**: [07_FIRST_WEEK_PLAN](07_FIRST_WEEK_PLAN.md) and [10_HANDS_ON_EXERCISES](10_HANDS_ON_EXERCISES.md)
5. **When stuck**: [11_TROUBLESHOOTING](11_TROUBLESHOOTING.md)

## Related Docs (Outside This Folder)

- `docs/ARCHITECTURE.md` – Detailed architecture
- `docs/read-this-first/06_LOCAL_DEV.md` – Local dev reference (Docker, make, Postman)
- `docs/PROBLEM_STATEMENT_AND_OVERVIEW.md` – Problem statement and benefits
- `docs/security/` – Auth, OAuth migration, dev setup
- `.cursor/rules/` – Cursor rule files that guide AI and developers
