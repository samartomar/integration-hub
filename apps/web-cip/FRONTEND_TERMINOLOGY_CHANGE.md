# Frontend Terminology Change: Vendor → Licensee

## Summary

The domain term in user-facing language has been updated from **Vendor** to **Licensee** across the Integration Hub frontend, documentation, and AI prompts. This is a **terminology-only** change; the system behavior and data model are unchanged.

## What Changed

### User-facing text (UI labels, messages, headings)

- "Vendor" → "Licensee", "Vendors" → "Licensees"
- Examples: "Vendor code" → "Licensee code", "Vendor name" → "Licensee name"
- "Edit Vendor" / "Create Vendor" → "Edit Licensee" / "Create Licensee"
- "Vendor Key" badge → "Licensee Key"
- "Target Vendor" → "Target Licensee"
- "Active Vendor" → "Active Licensee"
- Registry tab label "Vendors" → "Licensees"
- Error messages, help text, empty-state text updated accordingly

### Documentation

- `FRONTEND_IMPLEMENTATION.md` – domain term "licensee" in descriptions
- `docs/ARCHITECTURE.md` – "vendors" → "licensees" in prose and diagrams
- `ai/agent-system-prompt.txt` – natural-language descriptions updated
- `ai/tool-schema.json`, `ai/list-operations-schema.json` – description text updated
- `ai/README.md` – example prompt text updated

## What Did NOT Change

- **Database objects**: Tables and columns remain `vendor_*`, `source_vendor`, `target_vendor`, etc.
- **API request/response field names**: `sourceVendor`, `targetVendor`, `vendorCode`, `vendor_code`, `vendorName`, `vendor_name` unchanged in wire contracts
- **API route paths**: `/v1/registry/vendors`, etc. unchanged
- **Environment variables**: existing vendor-oriented names remain in shared/vendor surfaces where still used
- **Secret names**: `VENDOR_API_KEY`; admin uses JWT (no ADMIN_SECRET)
- **Function names**: `getVendorApiKeyForVendor`, `listVendors`, `onboardVendor`, etc. unchanged
- **Component and type names**: `VendorModal`, `VendorContractModal`, `vendorStorage` etc. unchanged (code identifiers)

## Rationale

The business term "Licensee" better reflects the contractual relationship in the domain. The underlying APIs and database schema continue to use "vendor" for technical consistency and to avoid costly migrations.
