#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://api.vera-api.xyz}"

echo "Checking ${BASE_URL}/health"
curl --fail --silent --show-error "${BASE_URL}/health"
echo

echo "Checking ${BASE_URL}/health/deep"
curl --fail --silent --show-error "${BASE_URL}/health/deep"
echo

echo "Health checks passed."
