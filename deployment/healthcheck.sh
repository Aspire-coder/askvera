#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://api.vera-api.xyz}"

check_json_endpoint() {
  local path="$1"
  local expected_status="${2:-200}"
  local tmp_file
  local status
  tmp_file="$(mktemp)"
  status="$(curl --silent --show-error --output "${tmp_file}" --write-out "%{http_code}" "${BASE_URL}${path}")"
  if [[ "${status}" != "${expected_status}" ]]; then
    echo "${path} returned HTTP ${status}, expected ${expected_status}." >&2
    cat "${tmp_file}" >&2
    rm -f "${tmp_file}"
    return 1
  fi
  python3 -m json.tool "${tmp_file}" >/dev/null
  cat "${tmp_file}"
  echo
  rm -f "${tmp_file}"
}

echo "Checking ${BASE_URL}/health"
check_json_endpoint "/health" 200

echo "Checking ${BASE_URL}/health/deep"
check_json_endpoint "/health/deep" 200

echo "Health checks passed."
