#!/usr/bin/env bash
# Run reset_and_seed.sql against DATABASE_URL.
# Usage: DATABASE_URL=postgresql://... ./tooling/scripts/aws_reset_and_seed.sh
# Or in CodeBuild/Lambda context: ensure DATABASE_URL is set, then run this script.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL is not set"
  echo "Usage: DATABASE_URL=postgresql://user:pass@host:5432/dbname ./tooling/scripts/aws_reset_and_seed.sh"
  exit 1
fi

psql "$DATABASE_URL" -f "$SCRIPT_DIR/reset_and_seed.sql"
echo "Done: reset_and_seed.sql applied"
