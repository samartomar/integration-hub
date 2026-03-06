# First Week Plan

Suggested plan for new engineers joining the Integration Hub team.

---

## Day 1: Orientation

### Morning

1. **Read docs (in order)**
   - [01_OVERVIEW.md](01_OVERVIEW.md)
   - [02_GLOSSARY.md](02_GLOSSARY.md)
   - [03_ARCHITECTURE.md](03_ARCHITECTURE.md)

2. **Skim vision and rules**
   - `.cursor/rules/strategy/00-vision.mdc`
   - `.cursor/rules/00-index.mdc`
   - `.cursor/rules/context/00-context.mdc`

### Afternoon

3. **Clone, install, run locally**
   - `git clone <repo> && cd py-poc`
   - `pip install -e ".[dev]"`
   - `make local-up`
   - `make local-health`

4. **Execute a request**
   - Use curl or Postman (see [06_LOCAL_DEV.md](06_LOCAL_DEV.md))
   - Run GET_RECEIPT (LH001 → LH002)
   - Inspect response; check `data_plane.transactions` via psql or admin API

---

## Day 2: Concepts & Flow

### Morning

1. **Read**
   - [04_KEY_CONCEPTS.md](04_KEY_CONCEPTS.md)
   - [05_RUNTIME_FLOW.md](05_RUNTIME_FLOW.md)

2. **Trace the execute path**
   - Open `apps/api/src/lambda/routing_lambda.py`
   - Follow handler from auth → allowlist → contract → mapping → endpoint → downstream
   - Identify where each of the 11 pipeline steps happens

### Afternoon

3. **Explore DB schema**
   - `control_plane.vendors`, `operations`, `vendor_operation_allowlist`
   - `vendor_endpoints`, `vendor_operation_contracts`, `vendor_operation_mappings`
   - `data_plane.transactions`, `audit_events`

4. **Read rule files (execution-focused)**
   - `.cursor/rules/data-model/00-contracts.mdc`, `.cursor/rules/data-model/01-mappings.mdc`, `.cursor/rules/data-model/02-endpoints.mdc`
   - `.cursor/rules/governance/00-allowlist-access.mdc`, `.cursor/rules/runtime/00-execute-runtime.mdc`

---

## Day 3: Codebase Navigation

### Morning

1. **Read**
   - [08_HOW_TO_NAVIGATE_CODEBASE.md](08_HOW_TO_NAVIGATE_CODEBASE.md)
   - [09_RULES_GUIDE.md](09_RULES_GUIDE.md)

2. **Map key modules**
   - `contract_utils.py` – `load_effective_contract`
   - `endpoint_utils.py` – `load_effective_endpoint`
   - `routing/transform.py` – `apply_mapping`
   - `canonical_error.py` – error helpers

### Afternoon

3. **Run tests**
   - `pytest tests/ -v`
   - Identify tests for routing, contract, mapping, endpoint logic

4. **Vendor portal**
   - Start web-partners (see `apps/web-partners/README.md`)
   - Log in (Auth0 or local), browse endpoints, mappings, allowlist

---

## Day 4: Hands-On

1. **Complete exercises** from [10_HANDS_ON_EXERCISES.md](10_HANDS_ON_EXERCISES.md)
2. **Make a small change**
   - Add a log line in `routing_lambda.py` and verify it appears
   - Or: add a new operation to seed and test execute
3. **Pair with teammate** on a real ticket (if available)

---

## Day 5: Deep Dive

1. **Pick one area** to go deeper:
   - Auth (JWT, `jwt_auth.py`, `vendor_identity.py`)
   - AI Gateway (PROMPT vs DATA, `ai_gateway_lambda.py`)
   - Change requests (`approval_utils.py`, `vendor_change_requests`)
   - CDK / infra (`infra/`, buildspecs)

2. **Read relevant docs**
   - `docs/PROBLEM_STATEMENT_AND_OVERVIEW.md`
   - `docs/security/04-dev-setup-guide.md`
   - `docs/ARCHITECTURE.md` (full)

3. **Document questions** for follow-up with team

---

## Checklist

By end of week 1, you should be able to:

- [ ] Run the Hub locally with `make local-up`
- [ ] Execute a GET_RECEIPT request and see a successful response
- [ ] Explain the 11 steps of the execute pipeline
- [ ] Define: effective contract, effective mapping, effective endpoint, allowlist
- [ ] Know where routing, contract, mapping, and endpoint logic live
- [ ] Run pytest and interpret results
- [ ] Use `.cursor/rules` when touching auth, contracts, or runtime

---

Next: [08_HOW_TO_NAVIGATE_CODEBASE.md](08_HOW_TO_NAVIGATE_CODEBASE.md)
