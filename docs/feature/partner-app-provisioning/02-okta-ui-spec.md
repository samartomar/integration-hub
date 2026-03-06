# Okta Partner App Provisioning – UI Spec

## Personas

- **Admin** – Provisions OAuth apps for partners during onboarding

---

## Screens & Components

### 1. Vendor Detail / Onboarding – "Provision OAuth App" Action

**Location:** Admin Portal, vendor detail or onboarding flow

**Trigger:** Button "Provision OAuth App" (visible when vendor exists and no app is provisioned)

**Behavior:**
1. Admin clicks "Provision OAuth App"
2. Confirmation modal: "Create OAuth 2.0 app for {vendor_code} ({vendor_name})? Partner will receive client_id and client_secret."
3. On confirm: call backend `POST /v1/registry/partners/{vendor_code}/provision-app`
4. Loading state (spinner)
5. Success: modal shows:
   - **client_id** (copy button)
   - **client_secret** (copy button, masked by default, "Show" toggle)
   - Warning: "Save these credentials. The secret will not be shown again."
   - Instructions: "Partner uses Client Credentials grant to obtain JWT. Token URL: {OKTA_TOKEN_URL}, Audience: {AUDIENCE}"
6. Error: toast + error message from API

### 2. Provisioned App Status

**Location:** Vendor detail page

**Display:**
- If app provisioned: badge "OAuth App: Provisioned" with app id or client_id (truncated)
- Link/button "Rotate client secret" (calls Okta API to regenerate; new secret shown once)
- "Deactivate app" (soft disable in Okta; partner can no longer obtain tokens)

### 3. Credential Delivery (Optional)

- "Email credentials to partner" – optional action that sends secure link (time-limited) to partner contact email
- Or: admin manually copies and sends via secure channel

---

## Wireframes (Conceptual)

```
┌─────────────────────────────────────────────────────────┐
│ Vendor: LH030 - Partner Corp Inc.                        │
├─────────────────────────────────────────────────────────┤
│ Status: Active                                           │
│ OAuth App: ● Provisioned (client_xxx...yyy)              │
│            [Rotate Secret] [Deactivate App]              │
│                                                         │
│ [Provision OAuth App]  (shown only when not provisioned)│
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ OAuth App Created                                        │
├─────────────────────────────────────────────────────────┤
│ client_id:     abc123xyz...                    [Copy]    │
│ client_secret: ••••••••••••••••••  [Show]      [Copy]    │
│                                                         │
│ ⚠ Save these credentials. The secret will not be       │
│   shown again.                                          │
│                                                         │
│ Token URL: https://dev-xxx.okta.com/oauth2/default/v1/token │
│ Audience:  urn:integrationhub:api                        │
│                                                         │
│                                    [Done] [Email Partner]│
└─────────────────────────────────────────────────────────┘
```

---

## API Contract (Backend)

### POST /v1/registry/partners/{vendor_code}/provision-app

**Auth:** Admin JWT

**Response 201:**
```json
{
  "vendor_code": "LH030",
  "client_id": "0oa1b2c3d4e5f6g7h",
  "client_secret": "xyz_secret_one_time_only",
  "token_url": "https://dev-xxx.okta.com/oauth2/default/v1/token",
  "audience": "urn:integrationhub:api"
}
```

**Errors:** 400 (vendor not found), 409 (app already provisioned), 502 (Okta API error)
