#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${BASE_URL:-}" ]]; then
  echo "BASE_URL is required (example: https://admin-api.example.com)"
  exit 1
fi

if [[ -z "${ADMIN_TOKEN:-}" ]]; then
  echo "ADMIN_TOKEN is required"
  exit 1
fi

tmp_topology="$(mktemp)"
tmp_activity="$(mktemp)"
trap 'rm -f "$tmp_topology" "$tmp_activity"' EXIT

echo "Checking mission control topology endpoint..."
topology_status="$(
  curl -sS -o "$tmp_topology" -w "%{http_code}" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    "${BASE_URL%/}/v1/registry/mission-control/topology"
)"

if [[ "$topology_status" != "200" ]]; then
  echo "Topology check failed with HTTP ${topology_status}"
  cat "$tmp_topology"
  exit 1
fi

echo "Checking mission control activity endpoint..."
activity_status="$(
  curl -sS -o "$tmp_activity" -w "%{http_code}" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    "${BASE_URL%/}/v1/registry/mission-control/activity"
)"

if [[ "$activity_status" != "200" ]]; then
  echo "Activity check failed with HTTP ${activity_status}"
  cat "$tmp_activity"
  exit 1
fi

python - <<'PY' "$tmp_activity"
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    payload = json.load(f)
if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
    raise SystemExit("Activity response missing items array")
print(f"Activity items count: {len(payload['items'])}")
PY

echo "Checking that sensitive payload fields are absent..."
if grep -E -i -q '"(request_body|response_body|payload)"' "$tmp_activity"; then
  echo "Forbidden payload key detected in mission control activity response"
  cat "$tmp_activity"
  exit 1
fi

echo "Mission Control verification passed."
