#!/usr/bin/env bash
# Build the integrationhub-common Lambda layer.
# Creates python/ with pip-installed deps, suitable for CDK Code.from_asset().
# Run from repo root: ./layers/integrationhub-common/build.sh
#
# Idempotent: cleans previous build artifacts before building.
# Uses Python 3.11 to match Lambda runtime.
# On Linux (CodeBuild): uses native pip. On Windows/Mac: uses --platform manylinux.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAYER_DIR="$SCRIPT_DIR"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_DIR="$REPO_ROOT/.bundled/integrationhub-common-layer"

cd "$REPO_ROOT"

# Clean previous build (idempotent)
rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

# Lambda layer expects /opt/python/ at runtime, so dir root must have "python/"
echo "Installing layer dependencies (Python 3.11)..."
if [[ "$(uname -s)" == "Linux" ]]; then
  pip install -r "$LAYER_DIR/requirements.txt" -t "$OUTPUT_DIR/python" --upgrade
else
  pip install -r "$LAYER_DIR/requirements.txt" -t "$OUTPUT_DIR/python" --upgrade \
    --platform manylinux2014_x86_64 \
    --python-version 3.11 \
    --only-binary=:all: 2>/dev/null || \
    pip install -r "$LAYER_DIR/requirements.txt" -t "$OUTPUT_DIR/python" --upgrade
fi

echo "Layer built at: $OUTPUT_DIR"
ls -la "$OUTPUT_DIR/python/" 2>/dev/null | head -15 || true
