# Integration Hub – Overview

## What Is the Integration Hub?

The Integration Hub centralizes how partners and internal/external systems exchange data. Instead of every vendor integration becoming a costly custom project, the Hub provides a **contract-driven framework** that:

- Validates data
- Governs access (who may call whom)
- Logs every action
- Ensures trustworthy interoperability at scale

**In one sentence:** Partners integrate once with the Hub; the Hub handles multiple providers, formats, and governance.

---

## Why It Exists

Organizations working with multiple external partners face:

| Problem | Solution |
|---------|----------|
| Fragmented integrations | One central broker with canonical contracts |
| No single control point | Admin-defined allowlist, contracts, mappings |
| Governance gaps | Change-request workflow; admins approve or reject |
| Limited intelligence | AI Gateway (Bedrock) for natural-language and DATA assist |

---

## Who Uses It

### Admin (Platform Owner / Governance)

- Defines canonical models and global standards
- Approves or rejects vendor-proposed changes
- Establishes who may call whom and in which directions
- Monitors operations, health, audits, and compliance

### Vendor (Partner Developer / Integrator)

- Configures how their system interacts with the Hub
- Provides endpoint, mapping, and optional contract overrides
- Tests and validates without impacting others
- Submits change requests (e.g. allowlist) for admin approval

### Runtime Caller (Apps, Internal Services, AI)

- Sends canonical-form requests
- Receives canonical-form responses
- Does not need to understand vendor-specific formats

---

## Key Flows

1. **Vendor Onboarding** – Vendor configures operations, endpoints, mappings. Admin approves. Vendor becomes production-ready.
2. **Execution** – Runtime caller sends canonical request → Hub validates, transforms, routes, returns canonical response with audit logging.
3. **Governance** – Admin defines models, access rules, observes metrics and audits.

---

## What the Hub Is *Not*

- **Not** an ETL or data sync platform
- **Not** a low-code automation tool
- **Not** a mechanism for cross-vendor data visibility
- **Not** designed for bulk transfer or batch pipelines
- **Not** a replacement for identity, billing, or compliance systems—it integrates with them

---

## Four Planes

| Plane | Purpose |
|-------|---------|
| **Control Plane** | Admin registry: vendors, operations, allowlist, endpoints, contracts, mappings, change requests |
| **Vendor Plane** | Vendor portal + vendor APIs for self-service |
| **Runtime Plane** | Execute transactions (validate → transform → route → record) |
| **AI Gateway** | PROMPT (conversational agent) + DATA (execute + optional formatter) |

---

## Auth at a Glance

- **JWT** from Auth0 is the source of truth for vendor identity
- Vendor code comes from a **single JWT claim** (e.g. `vendor_code`)
- **No vendor-facing API keys**—no `x-vendor-code` headers; no vendor identity from headers or body
- Local dev: Auth0 dev tenant or local JWT signer

---

Next: [02_GLOSSARY.md](02_GLOSSARY.md)
