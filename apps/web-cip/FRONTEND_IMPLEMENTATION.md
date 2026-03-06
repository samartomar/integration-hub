# Integration Hub Frontend — Implementation Details

React + TypeScript + Vite applications for the Integration Hub POC. This document describes the split architecture, shared package, routing, and how to run each app.

---

## 1. App Split Overview

| App | Path | Purpose |
|-----|------|---------|
| **web-cip** | `apps/web-cip/` | Admin + AI — Dashboard, Transactions, Registry, Debug, AI tab |
| **web-partners** | `apps/web-partners/` | Vendor persona — Home, Operations, Allowlist, Auth, Endpoints, Contracts, Onboarding, Execute |
| **ui-shared** | `packages/ui-shared/` | Shared types, API client factory, utilities, generic components |

---

## 2. Tech Stack (Shared)

| Tool | Version | Purpose |
|------|---------|---------|
| React | 19.x | UI framework |
| TypeScript | 5.9 | Typing |
| Vite | 7.x | Build tool & dev server |
| React Router | 7.x | Client-side routing |
| TanStack Query | 5.x | Server state, caching |
| Axios | 1.x | HTTP client |
| Tailwind CSS | 4.x | Styling |

- **frontend** also uses Recharts for dashboard charts.

---

## 3. Shared Package (`packages/ui-shared`)

**Exports:**

- **Types:** `Transaction`, `Vendor`, `Operation`, `AllowlistEntry`, `Endpoint`, `VendorEndpoint`, `VendorContract`, `VendorMapping`, `AuthProfile`, etc.
- **Utils:** `getActiveVendorCode`, `setActiveVendorCode`, `getVendorApiKeyForVendor`, `setVendorApiKeyForVendor` (vendorStorage)
- **Utils:** `buildSkeletonFromSchema`, `buildExampleFromSchema` (schemaExample)
- **API client:** `createAdminApi`, `createVendorApi`, `createVendorApiPublic` (admin uses JWT)
- **Components:** `ModalShell`, `ErrorFallback`

Both web-cip and web-partners depend on ui-shared via `"packages/ui-shared": "file:../../packages/ui-shared"`.

---

## 4. Environment Variables

| Variable | Required | Used By | Purpose |
|----------|----------|---------|---------|
| `VITE_ADMIN_API_BASE_URL` | Yes | Both | Admin API base (audit, registry, redrive) |
| `VITE_ADMIN_APP_URL` | No | web-partners | Base URL of Admin app (for transaction links after Execute) |

Vite inlines env at build time. Restart dev server or rebuild after changes.

---

## 5. Routing

### Admin App (`frontend`)

| Path | Component | Purpose |
|------|-----------|---------|
| `/` | Redirect → `/admin/dashboard` | — |
| `/admin/dashboard` | `DashboardPage` | Admin dashboard |
| `/admin/transactions` | `TransactionsPage` | Transaction list |
| `/admin/transactions/:transactionId` | `TransactionDetailPage` | Transaction detail |
| `/admin/registry` | `RegistryPage` | Registry (vendors, ops, allowlist, endpoints) |
| `/admin/registry/vendors/:vendorCode` | `VendorDetailPage` | Vendor detail |
| `/ai` | `AIPage` | AI tab (execute via natural language) |
| `/dashboard`, `/transactions`, `/registry` | Redirect to `/admin/*` | Legacy redirects |
| `*` | `NotFoundPage` | 404 |

**Top nav:** Admin | AI

### Vendor App (`apps/web-partners`)

| Path | Component | Purpose |
|------|-----------|---------|
| `/` | `VendorHomePage` | Vendor home with setup checklist |
| `/home` | Redirect → `/` | — |
| `/operations` | `VendorOperationsPage` | My Operations (outbound/inbound) |
| `/allowlist` | `VendorAllowlistPage` | Allowlist add/remove |
| `/configuration/auth-profiles` | `VendorAuthProfilesPage` | Auth profiles |
| `/configuration/endpoints` | `VendorEndpointsConfigPage` | Endpoints + verification |
| `/configuration` | `VendorConfigurationPage` | Operation readiness + flow entry points |
| `/onboarding` | `OnboardingPage` | Register, receive API key |
| `/execute` | `ExecutePage` | Execute playground |

**Contracts & Mapping** (at `/contracts`): Tabbed layout with Supported Operations, Contracts, and Mappings. Editing opens modals. `?operation=GET_RECEIPT` deep link switches to Contracts tab.

1. **Step 1 – Supported operation**: Mark the operation as supported (or see allowlist callout if it’s on your allowlist but not supported).

**Entry & routing:**
- x
- No param but at least one supported op: selects first supported.
- No supported ops: empty state with links to pick from canonical list.

**Deep links:** `/contracts?operation=GET_RECEIPT` opens the flow for that operation. My Operations “Configure” and Home checklist cards link to `/contracts?operation=<OP>` when applicable.

**Top nav:** Vendor Portal header with Settings.

---

## 6. API Configuration

Both apps use the shared API client factory:

- **Admin app:** `adminApi` (VITE_ADMIN_API_BASE_URL), `runtimeApi` (VITE_RUNTIME_API_BASE_URL or default runtime domain).
- **Vendor app:** `adminApi` (for allowlist, auth profiles, registry lookups), `vendorApi`, `vendorApiPublic` (for onboarding).

Credentials from `localStorage`:

- JWT bearer token is the auth source for admin and vendor API requests.
- Vendor identity is derived server-side from JWT claim `bcpAuth`.

---

## 7. How to Run

```bash
# Admin + AI app
cd frontend
npm install
npm run dev      # → http://localhost:5173 (or next free port)

# Vendor app
cd apps/web-partners
npm install
npm run dev      # → http://localhost:5174 (or next free port)

# Build for production
cd frontend && npm run build
cd apps/web-partners && npm run build
```

---

## 8. File Structure

```
apps/web-cip/
├── src/
│   ├── main.tsx
│   ├── App.tsx           # Admin layout (sidebar: Dashboard, Transactions, Registry)
│   ├── routes.tsx
│   ├── api/
│   │   ├── client.ts     # Uses createAdminApi, createVendorApi from packages/ui-shared
│   │   └── endpoints.ts  # Admin + vendor API calls (for Admin + AI)
│   ├── components/
│   └── pages/            # Dashboard, Transactions, Registry, AIPage, etc.
└── package.json

apps/web-partners/
├── src/
│   ├── main.tsx
│   ├── VendorAppLayout.tsx
│   ├── routes.tsx
│   ├── api/
│   │   ├── client.ts
│   │   └── endpoints.ts  # Vendor + admin (allowlist, auth, registry) API calls
│   ├── components/
│   │   └── config/       # AuthProfileModal, VendorEndpointModal, etc.
│   └── pages/            # VendorHomePage, ExecutePage, OnboardingPage, etc.
└── package.json

packages/ui-shared/
├── src/
│   ├── index.ts
│   ├── types.ts
│   ├── api/createClients.ts
│   ├── utils/vendorStorage.ts
│   ├── utils/schemaExample.ts
│   └── components/
│       ├── ModalShell.tsx
│       └── ErrorFallback.tsx
└── package.json
```

---

## 9. Credential Storage

| Key | Purpose |
|-----|---------|
| `okta-token-storage` (or equivalent IdP storage key) | JWT/session token used by API calls (admin uses JWT) |
| `integrationHub.activeVendorCode` | Active licensee code |

Configure via Settings modal in each app.
