# Access rules UI + Backend improvment - design

## ADR Reference

This design is governed by `docs/adr/ADR-012-access-rules-scalability-pattern.md`.

## Context

The current Access Rules experience is acceptable for small local datasets, but it will not scale to production-like volumes (for example, 1200+ operations and 70+ vendors). Rendering and interacting with large nested rule tables in a single client-side dataset will become slow, hard to scan, and expensive to maintain.

This design defines a scalable model for both UI and backend so Access Rules remain fast, understandable, and safe.

## Problems to solve

- Large rule sets are expensive to fetch and render in one pass.
- Client-side grouping/filtering across thousands of rows becomes slow.
- Deep nested tables are hard to navigate and easy to break visually.
- Existing interactions do not provide predictable performance at high cardinality.

## Design goals

- Keep Access Rules responsive at large scale.
- Support explicit-pair rules only (no wildcard semantics).
- Minimize payload sizes and avoid full-table fetches.
- Make rule discovery and editing predictable for admins.
- Keep current add/edit modal workflows compatible.

## Non-goals

- No new wildcard model.
- No schema rewrite for allowlist rows.
- No replacement of existing auth or approval systems.

## Proposed architecture

### 1) Backend query model (server-driven)

Use server-side filtering, grouping, and pagination as the default behavior.

- Add operation-level aggregate listing endpoint behavior:
  - Group by operation.
  - Return counts only (`ruleCount`, `sourceCount`, `targetCount`, direction summary).
- Add paged detail query by operation:
  - Query params: `operationCode`, optional `sourceVendorCode`, `targetVendorCode`, `flowDirection`, `limit`, `cursor`.
  - Return only requested slice + `nextCursor`.
- Keep `limit` bounded (`1..200`) everywhere.

### 2) UI information architecture

Split the current experience into two levels:

- **Explorer (default):**
  - Operation-first list with counts and health/status indicators.
  - Fast search/typeahead against operation code + description.
- **Details (on demand):**
  - Expand/open operation details panel.
  - Show source-grouped rows loaded page-by-page from backend.
  - Avoid rendering all rules at once.

### 3) Interaction model

- Always load small pages; fetch more on explicit user action.
- Keep current add/edit/delete modal actions.
- After save/delete:
  - Refetch only affected query keys.
  - Keep focused operation in view.
  - Preserve current filter state.

### 4) Rendering strategy

- Do not render full nested table for full dataset.
- Use paged rows in details panel.
- Add virtualization only if necessary after server pagination is in place.

## API sketch

### Operation summaries

- `GET /v1/registry/allowlist/summary`
  - Params: `search`, `flowDirection`, `scope`, `limit`, `cursor`
  - Returns:
    - `items: [{ operationCode, ruleCount, sourceCount, targetCount, directions[] }]`
    - `nextCursor`

### Operation details

- `GET /v1/registry/allowlist/by-operation`
  - Params: `operationCode` (required), `sourceVendorCode`, `targetVendorCode`, `flowDirection`, `limit`, `cursor`
  - Returns:
    - `items: explicit pair rows`
    - `nextCursor`

### Mutations

- Keep existing `POST /v1/registry/allowlist` behavior for explicit pair creation (single and batch contract).
- Keep existing delete endpoint.

## Rollout plan

1. Add backend summary + details query paths.
2. Switch UI Access Rules default view to operation summary list.
3. Add operation details panel with paged source-grouped rows.
4. Keep old rendering path behind a temporary feature flag for rollback.
5. Remove old full-table rendering once validated.

## Risks and mitigations

- **Risk:** query complexity increases.
  - **Mitigation:** index review for `(operation_code, source_vendor_code, target_vendor_code, flow_direction, created_at)`.
- **Risk:** UX mismatch during transition.
  - **Mitigation:** preserve current add/edit modal and success messaging.
- **Risk:** stale data after mutation.
  - **Mitigation:** targeted query invalidation + immediate refetch for active views.

## Success criteria

- Access Rules initial load remains fast with large datasets.
- No full dataset fetch needed for normal user flow.
- Save/delete updates appear in current view without manual reload.
- Admin can find and edit rules within a few actions at scale.

## TO-DO - Minor

- Remove legacy API-key lifecycle code from `apps/api/src/lambda/onboarding_lambda.py` once onboarding is fully JWT-based.
- Retire `apps/api/src/lambda/vendor_identity.py` after all remaining API-key references are removed.

