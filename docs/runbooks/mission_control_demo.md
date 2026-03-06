# Mission Control Demo

## Goal
Demonstrate live integration traffic, policy governance, and system observability.

## Step 1 — Open Mission Control
Navigate to:

`/admin/mission-control`

Explain:
- Nodes represent vendors.
- Edges represent operations and allowed routes.
- Activity feed shows near real-time traffic and policy outcomes.

## Step 2 — Successful Execution
Trigger:

`POST /v1/execute`

Example:
- Vendor `LH001`
- Operation `verifyMember`
- Target Vendor `PayerA`

Expected result:
Edge briefly shows active, then success.

## Step 3 — Policy Denial
Remove allowlist rule.

Trigger execute again.

Mission Control shows:
- `POLICY_DENY`
- `decisionCode = ALLOWLIST_DENY`

Explain governance model:
allowlist + policy engine enforcement controls runtime access.

## Step 4 — Downstream Failure
Configure endpoint incorrectly.

Trigger execution.

Mission Control shows:
- `EXECUTE_ERROR`

Explain downstream monitoring:
mission control highlights runtime failures without exposing payload data.

## Step 5 — Review Activity Panel
Show `correlationId` and `transactionId` values from activity rows and trace them in audit pages for incident triage.
