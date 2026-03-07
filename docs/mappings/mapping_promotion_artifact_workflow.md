# Mapping Promotion Artifact Workflow

## Overview

The Mapping Promotion Artifact workflow is the next step after the [Mapping Proposal Package](mapping_proposal_workflow.md). It turns proposal packages into **code-first promotion artifacts** for manual application to mapping definitions. **Deterministic mappings remain authoritative.** No automatic apply. No runtime mutation. No persistence.

## Prerequisites

- **Proposal Package** has been generated (Suggest → Compare → Generate Proposal Package)
- Mapping definitions are **code-first** under `canonical_mappings/`
- AI suggestions are **advisory only**

## Workflow

### 1. Generate Proposal Package

First, run the proposal package flow to produce a structured proposal (see [Mapping Proposal Workflow](mapping_proposal_workflow.md)).

### 2. Generate Promotion Artifact

After a proposal package exists, run **Generate Promotion Artifact** to create a code-first review artifact:

- **Target definition file** – inferred path (e.g. `apps/api/src/schema/canonical_mappings/eligibility_v1_lh001_lh002.py`)
- **Recommended changes** – added, changed, unchanged field mappings
- **Python snippet** – suggested mapping definition code for manual copy/apply
- **Review checklist** – pre-defined items
- **Test checklist** – steps to validate after applying
- **Notes** – including "Promotion artifact only. No mapping definition was changed."

### 3. Generate Promotion Markdown

Run **Generate Promotion Markdown** to get a markdown artifact suitable for:

- Code review
- Export to docs
- Copy/paste into tickets

### 4. Review and Apply (Manual)

To promote into code-first mapping definitions:

1. **Review artifact** – use the review checklist
2. **Copy Python snippet** (or markdown) and apply manually to the target file
3. **Run mapping preview/validate tests**
4. **Run runtime preflight** before execute

## Design Principles

1. **Deterministic mappings remain authoritative** – runtime uses code-first definitions only
2. **AI suggestions remain advisory only** – never auto-applied
3. **No automatic apply** – no runtime mutation of mapping definitions
4. **No direct file writes** – promotion artifact does not touch `canonical_mappings/`
5. **Code-first** – artifact produces Python snippets for manual apply
6. **Admin-only** in this phase

## Target File Inference

The promotion artifact infers the target definition file from:

- **Operation code** → file prefix (e.g. `GET_VERIFY_MEMBER_ELIGIBILITY` → `eligibility`)
- **Version** → `v1`, `v2`, etc. (e.g. `1.0` → `v1`)
- **Source/target vendors** → lowercase vendor codes

Example: `eligibility_v1_lh001_lh002.py`

## API Endpoints

- **POST /v1/mappings/canonical/promotion-artifact** – returns full promotion artifact (including `pythonSnippet`, `markdown`)
- **POST /v1/mappings/canonical/promotion-artifact/markdown** – returns markdown-only artifact

Both require `proposalPackage` in the request body. Admin auth required. No persistence. No runtime execution. No mapping mutation.

## Related

- [Mapping Proposal Workflow](mapping_proposal_workflow.md) – prerequisite flow
- [Canonical Mapping Engine](canonical_mapping_engine.md) – mapping definitions and runtime
