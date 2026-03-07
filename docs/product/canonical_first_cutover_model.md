# Canonical-First Cutover Model

## Overview

For the supported slice, the improved canonical/runtime/mapping experience is now the **primary product path**. Old UI paths are superseded for the supported slice. This document describes the cutover model, single-path flows, and operation gating.

---

## Supported Slice

| Dimension | Value |
|-----------|-------|
| **Operations** | GET_VERIFY_MEMBER_ELIGIBILITY, GET_MEMBER_ACCUMULATORS |
| **Vendor pair** | LH001 → LH002 (source → target) |

This is the explicit product cutover scope. It is defined in:
- Backend: `apps/api/src/shared/supported_operation_slice.py`
- Frontend: `packages/ui-shared/src/supportedOperationSlice.ts`

---

## Single-Path Product Flow

### Admin

For supported operations, the primary flow is:

1. **Canonical reference** – Browse schemas and examples
2. **Flow Builder** – Design flow drafts, generate handoff packages
3. **Mapping governance / readiness / release** – Adoption workbench (Adoption | Mapping Readiness tabs)
4. **Runtime preflight / execute** – Operator guidance, mission control

**Primary governance surface:** Adoption workbench (`/admin/adoption`) with tabs Adoption | Mapping Readiness.

**Registry Operations tab:** For supported ops, actions include Open Canonical, Open Flow Builder, Open Mapping Governance, Open Runtime Preflight, plus Edit, Contract, Adoption.

### Vendor

For supported operations (when source vendor is LH001), the primary flow is the guided operation journey:

1. **Canonical Explorer** – Browse schemas
2. **Sandbox** – Validate requests
3. **AI Debugger** – Debug with enhancement
4. **Runtime Preflight** – Validate envelope
5. **Canonical Execute** – Run (DRY_RUN or EXECUTE)

**Primary entry:** Flow (`/flow`) – the guided journey. Operation selection is gated to supported ops when vendor is LH001.

---

## Operation Gating

- **Supported operations** use the new canonical-first flow directly.
- **Unsupported operations** remain on older flows until migrated. They are not shown as fully canonical-enabled in the vendor Flow journey when the vendor is in the supported pair.
- **Vendor Flow journey:** When active vendor is LH001, only supported operations appear in operation selectors. Other vendors see all operations (no fake capability for unsupported pairs).

---

## Routes

### Admin

| Route | Purpose |
|-------|---------|
| `/admin/operator-guide` | Operator Guide (primary; neutral URL) |
| `/admin/syntegris-operator-guide` | Redirect → `/admin/operator-guide` |
| `/admin/adoption` | Adoption workbench |
| `/admin/canonical-mapping-readiness` | Redirect → `/admin/adoption?tab=readiness` |
| `/admin/syntegris-adoption` | Redirect → `/admin/adoption` |

### Vendor

| Route | Purpose |
|-------|---------|
| `/flow` | Guided operation journey (primary) |
| `/canonical`, `/sandbox`, `/ai-debugger`, `/runtime-preflight`, `/canonical-execute` | Standalone tool pages (contextual) |

---

## What Remains to Migrate

- Operations outside GET_VERIFY_MEMBER_ELIGIBILITY and GET_MEMBER_ACCUMULATORS
- Vendor pairs other than LH001 → LH002

These continue on existing paths. As they are cut over, update `supported_operation_slice.py` and `supportedOperationSlice.ts`.

---

## Related

- [UI Convergence Plan](./syntegris_ui_convergence_plan.md)
- [Feature Production Readiness](../release/syntegris_feature_production_readiness.md)
