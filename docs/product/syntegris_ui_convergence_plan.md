# UI Convergence Plan

## Overview

This document describes the UI convergence pass that brings integration adoption capabilities into the existing admin and vendor product structure, replacing the previous parallel scaffolding with a unified experience.

**No functionality was removed.** All pages remain reachable; only navigation, grouping, and contextual linking changed.

---

## Before vs After

### Admin – Before

- 10+ top-level nav items: Registry, Canonical, Flow Builder, Sandbox, AI Debugger, Runtime Preflight, Canonical Execute, Canonical Mappings, Mapping Readiness, Adoption
- Duplicate Operator Guide entries
- Tool pages (Sandbox, AI Debugger, etc.) as primary nav
- Adoption and Readiness as separate destinations

### Admin – After

- **Primary nav:** Dashboard, Transactions, Mission Control, Registry, Canonical, Flow Builder, Adoption, Operator Guide, AI
- **Adoption** is a single governance workbench with tabs: Adoption | Mapping Readiness
- Tool pages (Sandbox, AI Debugger, Runtime Preflight, Canonical Execute, Canonical Mappings) remain at their routes but are **not** in top-level nav; reached via Canonical, Adoption, or Operator Guide
- Operator Guide appears once

### Vendor – Before & After

- **Flow** was already the main entry for the operation journey
- FlowJourneyPage renders: Canonical Explorer → Sandbox → AI Debugger → Runtime Preflight → Canonical Execute
- Standalone routes (/canonical, /sandbox, etc.) remain for deep linking; they are not in main nav
- No change to vendor nav structure; Flow is the primary guided operation experience

---

## Admin Ownership

| Surface | Purpose |
|---------|---------|
| **Registry** | Licensees, Operations, Access rules, Access requests |
| **Canonical** | Browse canonical operations and schemas |
| **Flow Builder** | Design flow drafts, generate handoff packages |
| **Adoption** | Governance workbench: Adoption inventory + Mapping Readiness + Release bundle |
| **Operator Guide** | End-to-end flow reference; links to all tools and Adoption |
| **Mission Control** | Operational view of transactions |
| **Dashboard / Transactions** | Home, audit |

Tool pages (Sandbox, AI Debugger, Runtime Preflight, Canonical Execute, Canonical Mappings) are **contextual**—linked from Canonical, Adoption, Operator Guide, or deep links.

---

## Vendor Ownership

| Surface | Purpose |
|---------|---------|
| **Flow** | Main guided operation journey (5 steps) |
| **Flows** | List of flows |
| **Configuration** | Contract, endpoint, mapping, access |
| **Operations / Transactions** | Transaction history |
| **Execute** | Direct execute test |

The Flow journey is the primary guided operation experience for vendors. Steps: Canonical Explorer → Sandbox → AI Debugger → Runtime Preflight → Canonical Execute.

---

## Routes

### Admin

| Route | Page | Nav |
|-------|------|-----|
| `/admin/adoption` | AdoptionWorkbenchPage (tabs: Adoption, Readiness) | Adoption |
| `/admin/adoption?tab=readiness` | Same, Readiness tab | — |
| `/admin/syntegris-adoption` | Redirect → `/admin/adoption` | — |
| `/admin/canonical-mapping-readiness` | Redirect → `/admin/adoption?tab=readiness` | — |
| `/admin/canonical` | CanonicalExplorerPage | Canonical |
| `/admin/flow-builder` | FlowBuilderPage | Flow Builder |
| `/admin/sandbox` | SandboxPage | Contextual |
| `/admin/ai-debugger` | AIDebuggerPage | Contextual |
| `/admin/runtime-preflight` | RuntimePreflightPage | Contextual |
| `/admin/canonical-execute` | CanonicalExecutePage | Contextual |
| `/admin/canonical-mappings` | CanonicalMappingPage | Contextual |
| `/admin/syntegris-operator-guide` | SyntegrisOperatorGuidePage | Operator Guide |

### Vendor

| Route | Page | Nav |
|-------|------|-----|
| `/flow` | FlowJourneyPage (5-step journey) | Flow |
| `/canonical` | PartnerCanonicalExplorerPage | Via Flow |
| `/sandbox` | PartnerSandboxPage | Via Flow |
| `/ai-debugger` | PartnerAIDebuggerPage | Via Flow |
| `/runtime-preflight` | PartnerRuntimePreflightPage | Via Flow |
| `/canonical-execute` | PartnerCanonicalExecutePage | Via Flow |

---

## Contextual Additions

### Registry Operations tab

- **Adoption** link per operation row → `/admin/adoption?operationCode={code}`

### Adoption workbench

- Deep links to Canonical Mappings, Mapping Readiness, Flow Builder, Runtime Preflight, Canonical Execute, Operator Guide (with operation/vendor prefill)

### Operator Guide

- Links to Adoption workbench (replacing Mapping Readiness as separate step)
- Links to all tool pages

### Vendor Flow journey

- **Next step** link at bottom of each section (except last) → scrolls to next milestone

---

## Route State / Prefill

Existing prefill logic is preserved:

- `operationCode`, `version`, `sourceVendor`, `targetVendor` as query params
- CanonicalMappingPage, CanonicalMappingReadinessPage, FlowBuilderPage, RuntimePreflightPage, CanonicalExecutePage read these and prefill

---

## Files Changed

- `apps/web-cip/src/components/TopBar.tsx` – Nav consolidation, duplicate Operator Guide removed
- `apps/web-cip/src/routes.tsx` – Adoption route, redirects for legacy paths
- `apps/web-cip/src/pages/AdoptionWorkbenchPage.tsx` – New governance workbench shell
- `apps/web-cip/src/pages/SyntegrisOperatorGuidePage.tsx` – Adoption workbench link
- `apps/web-cip/src/pages/RegistryPage.tsx` – Adoption link in Operations table
- `apps/web-partners/src/pages/FlowJourneyPage.tsx` – Next-step links between milestones

---

## Related

- [Feature Production Readiness](../release/syntegris_feature_production_readiness.md)
- [Adoption Workbench](../adoption/syntegris_adoption_workbench.md)

**Note:** Legacy route paths (e.g. `/admin/syntegris-adoption`, `/admin/syntegris-operator-guide`) and internal identifiers may retain older naming for backward compatibility. User-facing labels use neutral terms (Adoption, Operator Guide, etc.).
