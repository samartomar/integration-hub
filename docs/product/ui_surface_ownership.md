# UI Surface Ownership

This document describes which UI surfaces (apps) own which product capabilities in the Integration Hub.

## Admin (web-cip)

Admin surfaces are for platform owners and governance:

- **Registry** – canonical models, operations, contracts, allowlist, endpoints, auth profiles
- **Mission Control** – topology, activity, policy decisions (admin-only)
- **Flow Builder** – admin flow design (mappings, contracts, endpoints for any vendor) (admin-only)
- **Policy / Governance** – policy simulator, feature gates, change requests, approvals
- **Transactions** – audit, transaction list, redrive
- **Onboarding** – vendor registration (admin-initiated)
- **Canonical Explorer** – browse canonical operation schemas (admin API)
- **Sandbox** – test canonical operations with mock execution (admin API)
- **AI Debugger** – analyze canonical requests, flow drafts, sandbox results (admin API)
- **Runtime Preflight** – validate canonical envelope (admin API)
- **Canonical Execute** – bridge canonical request to runtime (admin API)

## Partner (web-partners)

Partner surfaces are for vendor/partner developers and integrators:

- **Canonical Explorer** (`/canonical`) – browse canonical operation schemas and examples (read-only)
- **Sandbox** (`/sandbox`) – test canonical operations with mock execution (no vendor endpoints called)
- **AI Debugger** (`/ai-debugger`) – analyze canonical requests, flow drafts, and sandbox results
- **Runtime Preflight** (`/runtime-preflight`) – validate canonical envelope and resolve runtime prerequisites
- **Canonical Execute** (`/canonical-execute`) – bridge canonical request to runtime (DRY_RUN default, EXECUTE optional)
- **Flow Journey** (`/flow`) – milestone journey combining all five surfaces above
- **Configuration** – vendor-specific contracts, mappings, endpoints, access
- **Transactions** – vendor-scoped transaction list and details
- **Execute** – runtime execute test (AI/data)

## API Surface Split

- **Admin API** (`/v1/registry/*`, `/v1/sandbox/*`, `/v1/ai/debug/*`, `/v1/runtime/canonical/*`) – used by web-cip
- **Partner API** (`/v1/vendor/syntegris/*`) – used by web-partners for Syntegris surfaces

Backend services are shared; admin and partner APIs call the same domain logic. API surfaces and UIs are split by audience and policy.

## Vendor Identity Rules (Partner UI)

- Partner UI derives vendor identity from auth (JWT `bcpAuth`). Do not accept free-form `sourceVendor` input.
- Preflight and Canonical Execute: `sourceVendor` is derived from JWT; partner UI shows it as read-only (from active licensee).
- Target vendor remains selectable where product design requires choosing integration destination.

## Admin-Only Surfaces

- **Mission Control** – admin-only; not exposed in partner UI. Includes topology, activity, and canonical runtime transaction visibility. Reuses existing `data_plane.transactions` and `data_plane.audit_events`; no second transaction store.
- **Flow Builder** – admin-only in this phase (vendor has Flow Journey and Visual Builder for vendor-scoped flows)

## Mission Control Data Source

Mission Control reuses existing audit/transaction persistence. It does **not** introduce a second transaction store:

- **Transactions list/detail** – reads from `data_plane.transactions` and `data_plane.audit_events`
- **Topology** – derived from allowlist and vendors
- **Activity** – combines transactions + policy decisions (policy.policy_decisions)

Canonical fields (canonicalVersion, mode, etc.) are shown when stored or safely derivable from request bodies; missing fields produce notes rather than fabricated values.

## Mission Control: Metadata-Only / PHI-Safe

Mission Control is **metadata-only** and **PHI-safe**:

- **No payload exposure** – Request and response payload bodies are never exposed. Only safe metadata (operationCode, targetVendor, version, status, errorCode, httpStatus, etc.) is shown.
- **runtimeRequestPreview** – Contains only safe envelope metadata (operationCode, targetVendor, version, dryRun); no actual payload content.
- **responseSummary** – Contains errorCode, httpStatus, failureStage, and optionally key names only (no values); no response body content.
- **Canonical preflight/bridge activity** – Visible in Live Activity and Transactions with metadata only.
