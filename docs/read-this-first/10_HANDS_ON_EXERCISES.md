# Hands-On Exercises

Practical exercises to validate your understanding of the Integration Hub.

---

## Prerequisites

- `make local-up` has been run successfully
- `make local-health` returns OK for hub-api

---

## Exercise 1: Execute GET_RECEIPT

**Goal:** Successfully run the two-vendor GET_RECEIPT flow.

1. Using `curl` or Postman, send:
   ```bash
   curl -X POST http://localhost:8080/v1/execute \
     -H "Authorization: Bearer <your-jwt>" \
     -H "Content-Type: application/json" \
     -d '{"sourceVendor":"LH001","targetVendor":"LH002","operation":"GET_RECEIPT","value":{"txnId":"ex1"}}'
   ```
2. Verify you get a 200 response with `status` and `receiptId`.
3. Try with `/v1/integrations/execute` and JWT (Authorization: Bearer &lt;token&gt;) (omit `sourceVendor` from body).
4. Inspect the transaction: call `GET /v1/audit/transactions` (with JWT: Authorization Bearer) and find the latest transaction.

**Success:** Both execute paths return success; transaction is recorded.

---

## Exercise 2: Trigger ACCESS_DENIED

**Goal:** Understand allowlist enforcement.

1. Add a new vendor in seed (or use an existing one not in allowlist).
2. Call execute with `sourceVendor` that is **not** allowed to call `targetVendor` for `GET_RECEIPT`.
3. Verify you get `ACCESS_DENIED` (403 or error body with that code).
4. Confirm which allowlist rule would need to be added to permit the call.

**Success:** You can explain why the call was blocked and what rule would fix it.

---

## Exercise 3: Inspect Effective Contract

**Goal:** Trace where the effective contract is loaded.

1. Open `apps/api/src/lambda/routing_lambda.py`.
2. Find the call to `load_effective_contract` or `load_effective_contract_optional`.
3. Add a temporary log (e.g. `log_json({"effective_contract": ...})`) and run execute again.
4. Check logs to see which contract (canonical vs vendor override) was used for GET_RECEIPT.

**Success:** You can identify whether canonical or vendor contract was used for the flow.

---

## Exercise 4: Trace the Execute Pipeline

**Goal:** Map code to the 11 pipeline steps.

1. In `routing_lambda.py`, locate the handler function.
2. Create a checklist of the 11 steps (from [05_RUNTIME_FLOW.md](05_RUNTIME_FLOW.md)).
3. For each step, find the corresponding code block or function call.
4. Document line numbers or function names next to each step.

**Success:** You have a written mapping of steps → code.

---

## Exercise 5: Add a New Operation to Seed

**Goal:** Add an operation and test execute (with a mock or pass-through).

1. Find `tooling/scripts/seed_local.py` or equivalent seed script.
2. Add a new operation (e.g. `GET_INVOICE`).
3. Add canonical contract (if required by routing) and allowlist rule.
4. Run `make local-sync-db`.
5. Call execute for the new operation. (If no real endpoint exists, you may get `ENDPOINT_NOT_FOUND`—that's OK. The goal is to get past allowlist and contract validation.)

**Success:** New operation is in DB; execute reaches the endpoint-loading step (or fails there as expected).

---

## Exercise 6: Run Tests

**Goal:** Run the test suite and understand what's covered.

1. Run `pytest tests/ -v`.
2. Pick one failing or passing test related to routing or contracts.
3. Read the test; understand what it asserts.
4. Make a trivial change (e.g. add a comment) and confirm the test still passes.

**Success:** You can run tests and explain what at least one test does.

---

## Exercise 7: Use the Vendor Portal

**Goal:** Use the Vendor Portal UI.

1. Start the vendor portal (see `apps/web-partners/README.md`).
2. Log in with Auth0 (or configured local auth).
3. Navigate to: operations, endpoints, mappings, allowlist.
4. Identify where "Using canonical format" would appear (if canonical pass-through is used).
5. If change requests are supported, submit a mock allowlist change request and see it in PENDING.

**Success:** You can navigate the vendor portal and understand its main sections.

---

## Exercise 8: Change Request Flow (If Implemented)

**Goal:** Trace the change-request lifecycle.

1. Submit an allowlist change request via vendor API or portal.
2. Find the row in `control_plane.vendor_change_requests` (via SQL or admin API).
3. Approve or reject via admin API or registry.
4. Verify the allowlist is updated (or not) based on the decision.

**Success:** You understand how change requests move from PENDING → APPROVED/REJECTED.

---

## Bonus: Break Something (Safely)

1. In `routing_lambda.py`, temporarily comment out the allowlist check.
2. Run execute with a source/target combo that would normally be blocked.
3. Observe the call succeeds (or fails later).
4. Restore the check.

**Success:** You understand the role of the allowlist check in the pipeline.

---

## Completion Checklist

- [ ] Exercise 1: Execute GET_RECEIPT
- [ ] Exercise 2: Trigger ACCESS_DENIED
- [ ] Exercise 3: Inspect effective contract
- [ ] Exercise 4: Trace pipeline steps to code
- [ ] Exercise 5: Add new operation to seed
- [ ] Exercise 6: Run tests
- [ ] Exercise 7: Use vendor portal
- [ ] Exercise 8: Change request flow (if applicable)

---

Back to [00_INDEX.md](00_INDEX.md)
