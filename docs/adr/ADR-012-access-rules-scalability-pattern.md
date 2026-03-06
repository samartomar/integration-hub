# ADR-012: Access Rules Scalability Pattern

## Status

Accepted

## Date

2026-03-01

## Context

Access Rules will grow to large scale (e.g., 1200+ operations and 70+ vendors). The existing full-table fetch and render model does not scale for performance or usability.

We need a stable default pattern that keeps UI responsiveness high while preserving explicit allowlist semantics.

## Decision

Adopt an **operation-first, server-driven pagination** model for Access Rules in Admin UI.

- Default list shows **operation summaries** (counts only), not full rules.
- Rule rows are loaded **on demand** when a specific operation is expanded/opened.
- Detailed rows are fetched with **cursor pagination** and bounded limits.
- UI groups details by source vendor within an operation.
- Mutations (add/edit/delete) trigger **targeted query invalidation** and focused refetch.

## Invariants

- Explicit pair allowlist only (no wildcard behavior).
- API limits remain bounded (`1..200`).
- No full dataset fetch for normal user flow.
- Existing add/edit modal behavior stays compatible.

## Consequences

- Initial page load stays fast at high cardinality.
- Data transfer and render cost are controlled.
- Backend query paths become more specialized (summary vs detail).
- UI complexity shifts from rendering everything to orchestrating paged views.

## Implementation Notes

- Add/extend backend endpoints for:
  - operation summaries
  - operation-scoped paged details
- Change Access Rules default view to operation summaries.
- Keep old full-table path behind temporary fallback until validated, then remove.

Indexing note

Call out that we rely on an index like (operation_code, source_vendor_code, target_vendor_code) because the detailed view filters by operation and paginates on vendor pairs.

API shapes (very high level)

One summary endpoint: “list operations with counts of allowlist rules by direction.”

One detail endpoint: “list rules for {operation_code} with pagination & optional filters for source/target.”

Migration stance

One line: “Seed/demo data and future migrations must not create wildcard rules; if any exist, the UI should ignore them and an offline script should clean them up.”

## Alternatives Considered

- **Client-side only optimization** over full fetch: rejected (still too heavy at scale).
- **Immediate virtualization without server pagination**: rejected (reduces DOM cost but not payload/query cost).

