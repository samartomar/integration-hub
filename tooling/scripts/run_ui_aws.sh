#!/usr/bin/env bash
# Run Admin + Vendor portals with AWS API URLs (from env-config or .env.aws)
set -e
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

# Load VITE_* from env-config (custom domains)
eval "$(python tooling/scripts/load_env_config.py --vite 2>/dev/null)" 2>/dev/null || true
# Overlay .env.aws (user-specific URLs / Okta overrides)
[ -f .env.aws ] && set -a && . ./.env.aws && set +a

admin_okta_issuer="${VITE_OKTA_ISSUER_ADMIN:-${VITE_OKTA_ISSUER:-}}"
admin_okta_client_id="${VITE_OKTA_CLIENT_ID_ADMIN:-${VITE_OKTA_CLIENT_ID:-}}"
admin_okta_audience="${VITE_OKTA_AUDIENCE_ADMIN:-${VITE_OKTA_AUDIENCE:-}}"
admin_okta_scopes="${VITE_OKTA_SCOPES_ADMIN:-${VITE_OKTA_SCOPES:-}}"
admin_okta_redirect_uri="${VITE_OKTA_REDIRECT_URI_ADMIN:-${VITE_OKTA_REDIRECT_URI:-}}"
admin_okta_redirect_path="${VITE_OKTA_REDIRECT_PATH_ADMIN:-${VITE_OKTA_REDIRECT_PATH:-}}"

vendor_okta_issuer="${VITE_OKTA_ISSUER_VENDOR:-${VITE_OKTA_ISSUER:-}}"
vendor_okta_client_id="${VITE_OKTA_CLIENT_ID_VENDOR:-${VITE_OKTA_CLIENT_ID:-}}"
vendor_okta_audience="${VITE_OKTA_AUDIENCE_VENDOR:-${VITE_OKTA_AUDIENCE:-}}"
vendor_okta_scopes="${VITE_OKTA_SCOPES_VENDOR:-${VITE_OKTA_SCOPES:-}}"
vendor_okta_connection="${VITE_OKTA_CONNECTION_VENDOR:-${VITE_OKTA_CONNECTION:-}}"
vendor_okta_redirect_uri="${VITE_OKTA_REDIRECT_URI_VENDOR:-${VITE_OKTA_REDIRECT_URI:-}}"
vendor_okta_redirect_path="${VITE_OKTA_REDIRECT_PATH_VENDOR:-${VITE_OKTA_REDIRECT_PATH:-}}"

(
  cd apps/web-cip
  [ -n "$admin_okta_issuer" ] && export VITE_OKTA_ISSUER="$admin_okta_issuer"
  [ -n "$admin_okta_client_id" ] && export VITE_OKTA_CLIENT_ID="$admin_okta_client_id"
  [ -n "$admin_okta_audience" ] && export VITE_OKTA_AUDIENCE="$admin_okta_audience"
  [ -n "$admin_okta_scopes" ] && export VITE_OKTA_SCOPES="$admin_okta_scopes"
  [ -n "$admin_okta_redirect_uri" ] && export VITE_OKTA_REDIRECT_URI="$admin_okta_redirect_uri"
  [ -n "$admin_okta_redirect_path" ] && export VITE_OKTA_REDIRECT_PATH="$admin_okta_redirect_path"
  npm run dev
) &

(
  cd apps/web-partners
  [ -n "$vendor_okta_issuer" ] && export VITE_OKTA_ISSUER="$vendor_okta_issuer"
  [ -n "$vendor_okta_client_id" ] && export VITE_OKTA_CLIENT_ID="$vendor_okta_client_id"
  [ -n "$vendor_okta_audience" ] && export VITE_OKTA_AUDIENCE="$vendor_okta_audience"
  [ -n "$vendor_okta_scopes" ] && export VITE_OKTA_SCOPES="$vendor_okta_scopes"
  [ -n "$vendor_okta_connection" ] && export VITE_OKTA_CONNECTION="$vendor_okta_connection"
  [ -n "$vendor_okta_redirect_uri" ] && export VITE_OKTA_REDIRECT_URI="$vendor_okta_redirect_uri"
  [ -n "$vendor_okta_redirect_path" ] && export VITE_OKTA_REDIRECT_PATH="$vendor_okta_redirect_path"
  npm run dev
) &
echo "Admin: http://localhost:5173 | Vendor: http://localhost:5174"
wait
