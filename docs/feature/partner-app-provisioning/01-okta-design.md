# Okta Partner App Provisioning – Design

## Purpose

Per-partner OAuth 2.0 apps in Okta, created on demand during partner onboarding. Partners use client_id + client_secret to obtain JWTs and call Integration Hub APIs.

---

## Architecture

```
Partner Onboarding (Admin Portal)
         │
         ▼
POST /v1/registry/partners/{vendor_code}/provision-app
  (or extend existing vendor create/update)
         │
         ▼
Backend calls Okta Management API
  POST https://{org}.okta.com/api/v1/apps
         │
         ▼
Okta returns: app id, client_id, client_secret
         │
         ├─ Store in partner_oauth_apps (vendor_code, okta_app_id)
         └─ Return credentials to caller (one-time display)
```

---

## Okta Management API

### Create Application

**Endpoint:** `POST /api/v1/apps`

**Auth:** API Token (SSWS header) or OAuth 2.0 client credentials

**Headers:**
```
Authorization: SSWS {okta_api_token}
Content-Type: application/json
```

**Request Body (OAuth 2.0 Client Credentials):**
```json
{
  "name": "oidc_client",
  "label": "Integration Hub - LH030",
  "signOnMode": "OPENID_CONNECT",
  "credentials": {
    "oauthClient": {
      "token_endpoint_auth_method": "client_secret_post",
      "client_id": "auto",
      "client_secret": "auto"
    }
  },
  "settings": {
    "oauthClient": {
      "client_uri": "https://partners.example.com",
      "logo_uri": "",
      "response_types": ["token"],
      "grant_types": ["client_credentials"],
      "application_type": "service"
    }
  }
}
```

**Response:** Includes `id`, `credentials.oauthClient.client_id`, `credentials.oauthClient.client_secret` (client_secret shown only on create).

### Required Scopes

- `okta.apps.manage` (create/update/delete apps)
- Or `okta.apps.read` + `okta.apps.create`

### Authorize App for API

After creating the app, authorize it for your Custom Authorization Server (API):

- `POST /api/v1/authorizationServers/{authServerId}/clients`
- Or via Okta Admin UI: API → Authorization Servers → Default → Machine to Machine → Add Application

---

## Vendor Claim (lhcode) in Token

Okta must include `lhcode` (or `vendor_code`) in the access token. Options:

### Option A: Custom Claim (Authorization Server)

1. Authorization Server → Claims → Add Claim
2. Name: `lhcode`
3. Include in: Access Token
4. Value: Expression (e.g. `app.lhcode` if app has custom attribute)

### Option B: App Profile Attribute

1. Create custom app profile attribute: `lhcode`
2. Set per-app when creating: `profile.lhcode = vendor_code`
3. Configure claim to read from `app.lhcode`

### Option C: Okta Groups

1. Create group per vendor (e.g. "vendor-LH030")
2. Assign app to group
3. Claim expression: extract vendor code from group name

---

## Configuration (Environment)

| Variable | Purpose |
|----------|---------|
| `OKTA_DOMAIN` | e.g. `dev-12345.okta.com` |
| `OKTA_API_TOKEN` | Management API token (store in Secrets Manager) |
| `OKTA_AUTH_SERVER_ID` | Default or custom (e.g. `default`) |
| `OKTA_AUDIENCE` | API audience (e.g. `urn:integrationhub:api`) |
| `IDP_ISSUER` | `https://{OKTA_DOMAIN}/oauth2/{AUTH_SERVER_ID}` |
| `IDP_JWKS_URL` | `https://{OKTA_DOMAIN}/oauth2/{AUTH_SERVER_ID}/v1/keys` |

---

## Database (Optional)

Table to track provisioned apps:

```sql
CREATE TABLE control_plane.partner_oauth_apps (
  vendor_code   VARCHAR(32) NOT NULL REFERENCES control_plane.vendors(vendor_code),
  idp           VARCHAR(16) NOT NULL,  -- 'okta' | 'auth0'
  idp_app_id    VARCHAR(128) NOT NULL,
  client_id     VARCHAR(256) NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (vendor_code, idp)
);
```

`client_secret` is **not** stored; it is shown once at creation and delivered to the partner.

---

## Security

- API token: store in AWS Secrets Manager, rotate regularly
- client_secret: never log; return only in secure response; advise partner to store securely
- Use HTTPS for all Okta API calls
