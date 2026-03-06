# Integration Hub - Frontend

React + TypeScript + Vite app for the Integration Hub POC.

---

## Environment variables

Create `.env` from `.env.example` and configure:

- **`VITE_ADMIN_API_BASE_URL`** — Admin API base URL (audit, registry, redrive)

**Settings (topbar):** Debug panel toggle. Authentication uses Okta JWT.

---

## Run commands

```bash
# Install dependencies
npm install

# Development
npm run dev

# Production build
npm run build

# Preview production build
npm run preview

# Lint
npm run lint
```

---

## Pages

### Dashboard (`/dashboard`)

Summary cards (total, completed, failed, validation failed, downstream errors), line chart (transactions over time), donut chart (status breakdown), recent transactions table. Filter by vendor and date range (24h / 7d).

### Transactions (`/transactions`)

Filterable list (vendor, operation, status, date range, limit). Table with same columns as dashboard. Click row to open detail drawer with request/response JSON, audit timeline, and redrive button.

### Transaction detail (`/transactions/:id`)

Full transaction details with request/response bodies. Linked from dashboard table and Execute success response.

### Execute (`/execute`)

Execute Playground form: targetVendor, operation, idempotencyKey (with Generate), parameters (JSON). Submits to Vendor API execute endpoint. Shows response and link to transaction.

### Registry (`/registry`)

Tabs: **Vendors** (list + upsert), **Operations** (list + upsert), **Allowlist** (list + upsert), **Endpoints** (list + upsert). Requires Okta login.

### Onboarding (`/onboarding`)

Register vendor (vendorCode, vendorName, forceRotate). Calls Vendor API onboarding/register. Shows API key once with copy button. No API key required to access.
