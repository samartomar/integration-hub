# Auth0 Partner App Provisioning – Agent Implementation Guide

## Purpose

Implement automated per-partner OAuth app creation using Auth0 Management API. Use this guide when implementing the feature with Auth0 (current POC IdP).

---

## Auth0 Management API – Create Client

**Endpoint:** `POST https://{domain}/api/v2/clients`

**Auth:** Bearer token from Client Credentials grant (Management API audience)

**Request:**
```json
{
  "name": "Integration Hub - LH030",
  "app_type": "non_interactive",
  "grant_types": ["client_credentials"],
  "token_endpoint_auth_method": "client_secret_post",
  "client_metadata": {
    "lhcode": "LH030"
  }
}
```

**Response:** `client_id`, `client_secret` (secret only on create)

**Required Scopes:** `create:clients`

---

## Vendor Claim (lhcode) in Auth0 Token

Auth0 does not automatically include `client_metadata` in the token. Use an **Auth0 Action** (post-login or credential-exchange):

```javascript
exports.onExecutePostLogin = async (event, api) => {
  if (event.client.metadata && event.client.metadata.lhcode) {
    api.accessToken.setCustomClaim('lhcode', event.client.metadata.lhcode);
  }
};
```

Or for M2M only, use **Credential Exchange** action to add `lhcode` to the access token from `client.metadata.lhcode`.

---

## Implementation Tasks for Agent

1. **Backend – New endpoint or extend registry**
   - Add `POST /v1/registry/partners/{vendor_code}/provision-app`
   - Or extend vendor create/update to optionally provision app
   - Lambda: obtain Auth0 Management API token (client_credentials), call `POST /api/v2/clients`
   - Store `client_id` in `partner_oauth_apps` (create table if needed); never store `client_secret` in DB
   - Return `client_id`, `client_secret`, `token_url`, `audience` in response

2. **Auth0 configuration**
   - Create Auth0 Action to add `lhcode` from `client_metadata` to access token
   - Ensure API `urn:integrationhub:api` is authorized for new M2M clients (Auth0 Dashboard or API)

3. **Admin Portal UI**
   - Vendor detail: "Provision OAuth App" button
   - Modal: confirm → call API → display credentials with copy buttons
   - Show "OAuth App: Provisioned" status when app exists
   - Optional: "Rotate secret" (Auth0 `POST /api/v2/clients/{id}/rotate-secret`)

4. **Environment**
   - `AUTH0_MANAGEMENT_CLIENT_ID` – M2M app for Management API
   - `AUTH0_MANAGEMENT_CLIENT_SECRET` – in Secrets Manager
   - `AUTH0_DOMAIN` – existing

5. **DB migration**
   - `control_plane.partner_oauth_apps` table (vendor_code, idp, idp_app_id, client_id, created_at)

---

## Key Files to Touch

| Area | File |
|------|------|
| Backend | `registry_lambda.py` or new `provisioning_lambda.py` |
| Migration | `apps/api/migrations/versions/vXX_partner_oauth_apps.py` |
| Admin UI | Vendor detail component, modal for credentials |
| API routes | `data_plane_stack.py` (if new Lambda) or extend registry routes |
