# Mapping Proposal Workflow

## Overview

The Mapping Proposal Package workflow is the next safe step after Suggest/Compare. It produces a structured, review-only artifact that can be exported and promoted intentionally. **Deterministic mappings remain authoritative.** No automatic apply. No runtime mutation.

## Prerequisites

- **Suggest/Compare flow** already exists on the Canonical Mappings page
- Mapping definitions are **code-first** under `canonical_mappings/`
- AI suggestions are **advisory only**

## Workflow

### 1. Suggest Mapping

Run **Suggest Mapping** (with or without AI) to get:

- Deterministic baseline (field mappings, constants, warnings)
- Optional AI suggestion (advisory only)
- Optional comparison (unchanged, added, changed)

### 2. Compare Suggestion (Optional)

If AI suggestion is present, run **Compare Suggestion** to see field-level diff between existing mapping and AI proposal.

### 3. Generate Proposal Package

After Suggest (and optionally Compare), run **Generate Proposal Package** to create a structured review artifact:

- Proposal ID (UUID)
- Operation context (operationCode, version, sourceVendor, targetVendor, direction)
- Deterministic baseline
- AI suggestion (if present)
- Comparison (if present)
- **Review checklist** (pre-defined items)
- **Promotion guidance** (steps to promote manually)
- Notes (including "Proposal package only. No runtime mapping was changed.")

### 4. Generate Proposal Markdown

Run **Generate Proposal Markdown** to get a markdown artifact suitable for:

- Code review
- Export to docs
- Copy/paste into tickets

### 5. Review and Promote (Manual)

To promote a proposal into code-first mapping definitions:

1. **Review proposal manually** – use the review checklist
2. **Update code-first mapping definition** in `canonical_mappings/`
3. **Run mapping preview/validate tests**
4. **Re-run runtime preflight** before execute

## Design Principles

1. **Deterministic mappings remain authoritative** – runtime uses code-first definitions only
2. **AI suggestions remain advisory only** – never auto-applied
3. **No automatic apply** – no runtime mutation of mapping definitions
4. **No direct runtime mutation** – proposal package does not touch `canonical_mappings/`
5. **Proposal package is exportable/reviewable** – JSON and markdown artifacts
6. **Admin-only** in this phase

## Recommended Review Checklist

- [ ] Confirm canonical source fields are correct
- [ ] Confirm vendor target field paths are correct
- [ ] Confirm no required field is dropped
- [ ] Confirm suggestion is advisory only before promotion

## API Endpoints

- **POST /v1/mappings/canonical/proposal-package** – returns structured proposal package (JSON + optional markdown)
- **POST /v1/mappings/canonical/proposal-package/markdown** – returns markdown-focused artifact

Both require admin auth. No persistence. No runtime execution. No mapping mutation.
