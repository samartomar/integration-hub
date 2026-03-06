# UI Layout Spec (Vendor + Admin)

Last updated: 2026-03-03 (v2)

## Purpose
- Define one shared spacing/layout baseline across Vendor and Admin UIs.
- Keep pages readable, compact, and consistent without page-level hacks.

## Spacing Scale
- Base scale uses 4px steps: `4, 8, 12, 16, 20, 24, 32`.
- Prefer these Tailwind spacing classes:
  - `0.5` (2px), `1` (4px), `1.5` (6px), `2` (8px), `2.5` (10px), `3` (12px), `4` (16px), `5` (20px), `6` (24px), `8` (32px)

## Page Shell (Both Apps)
- Main content wrapper:
  - `px-3 sm:px-6 lg:px-8`
  - `py-4 sm:py-5 lg:py-6`
- Section rhythm default:
  - `space-y-6`

## Page Header (Both Apps)
- Title/subtitle spacing:
  - Title uses `mb-1`
  - Subtitle has no extra `mt-*` (avoid dual margin stacking)
- Header container:
  - `flex ... sm:items-start ...` (not stretch)
  - Prevent right-side controls from increasing header height unexpectedly.

## Sections and Rows
- High-level section gap: `space-y-6` (24px)
- Sub-block gap (within section): `gap-3` or `space-y-3`
- Dense control rows (chips/buttons): `gap-1.5` to `gap-2`

## Cards
- Standard stat/info card padding: `px-3 py-2.5`
- Card group gap: `gap-3`
- Optional hero stat-card variant (for dashboard/top summary only): `px-4 py-4` to `px-4 py-5`
- Do not mix standard and hero variants in the same row.

## Card Grid (New)
- Use a consistent card grid for summary rows:
  - `grid gap-3`
  - responsive columns (example): `grid-cols-1 sm:grid-cols-2 xl:grid-cols-4`
- Avoid ad-hoc flex wrapping for card rows unless the view explicitly requires it.

## Tables
- Header cells: `px-3 py-2`
- Body cells:
  - compact: `px-3 py-1.5`
  - standard: `px-3 py-2`
- Empty state row padding: `py-6` (compact) to `py-8` (standard)
- Empty state container baseline: `min-h-[120px] py-8`
- ID/URL/value truncation baseline:
  - `max-w-[200px] truncate`
  - use `font-mono text-xs` for long technical identifiers when appropriate

## Chips
- Chip padding: `px-2 py-0.5`
- Chip gap: `gap-1.5`
- Use `whitespace-nowrap` on chip labels.
- On desktop where possible, use `sm:flex-nowrap` for stable vertical rhythm.
- Apply the same chip padding across all pages (Flows, Transactions, Configuration).

## Filter/Action Bars (New)
- Standard action row container:
  - `flex flex-wrap items-center gap-2`
- Keep search, dropdowns, and action buttons inside one shared row pattern.
- Avoid page-specific gap inflation above `gap-2` without explicit UX need.

## Forms (New)
- Field stack baseline: `space-y-3`
- Label-to-input spacing: `mb-1`
- Helper/error text spacing: `mt-1`
- Input/select/textarea visual rhythm should align with compact table density.
- Form control height baseline:
  - input/select: `h-9` or `py-2 text-sm`
  - compact variant: `h-8` only for dense tool rows
- Required indicator style:
  - use a consistent marker (`*`) and style token (example: `text-red-500`)
  - keep marker placement consistent across Vendor and Admin forms

## Modals
- Body padding default: `p-5`
- Header pattern:
  - `bg-gray-50`
  - `border-b border-gray-200`
  - semibold title
  - close button at right
- Field stack: `space-y-3` (unless intentionally dense/compact)

## Tailwind Setup Standard
- Use build-time Tailwind only (Vite + PostCSS).
- Required:
  - `src/index.css` includes `@import "tailwindcss";`
  - app has `postcss.config.mjs` with `@tailwindcss/postcss`
- Do **not** use `https://cdn.tailwindcss.com` in app `index.html`.

## Implementation Rules
- Prefer shared layout/component classes over page-specific overrides.
- Page-specific spacing overrides are temporary and should be removed once shared classes are updated.
- Keep Vendor and Admin aligned unless a page has explicit product requirements.
- When a page intentionally diverges (for example hero cards), define an explicit variant in this doc first.
