#!/usr/bin/env bash
set -Eeuo pipefail

LOCAL_URL="${LOCAL_URL:-http://127.0.0.1:8000}"
PUBLIC_URL="${PUBLIC_URL:-${BASE_URL:-}}"
CURL_TIMEOUT_SECONDS="${CURL_TIMEOUT_SECONDS:-5}"

check_json_endpoint() {
  local label="$1"
  local base_url="$2"
  local path="$3"
  local expected_status="${4:-200}"
  local tmp_file
  local status
  local url="${base_url}${path}"

  tmp_file="$(mktemp)"
  if ! status="$(curl --silent --show-error --max-time "${CURL_TIMEOUT_SECONDS}" --output "${tmp_file}" --write-out "%{http_code}" "${url}")"; then
    echo "[fail] ${label} failed: ${url} did not respond within ${CURL_TIMEOUT_SECONDS}s." >&2
    rm -f "${tmp_file}"
    return 1
  fi

  if [[ "${status}" != "${expected_status}" ]]; then
    echo "[fail] ${label} failed: ${url} returned HTTP ${status}, expected ${expected_status}." >&2
    cat "${tmp_file}" >&2
    rm -f "${tmp_file}"
    return 1
  fi

  if ! python3 -m json.tool "${tmp_file}" >/dev/null; then
    echo "[fail] ${label} failed: ${url} did not return valid JSON." >&2
    cat "${tmp_file}" >&2
    rm -f "${tmp_file}"
    return 1
  fi

  rm -f "${tmp_file}"
  echo "[ok] ${label}"
}

check_json_endpoint "Local Health" "${LOCAL_URL}" "/health" 200
check_json_endpoint "Local Deep Health" "${LOCAL_URL}" "/health/deep" 200

if [[ -n "${PUBLIC_URL}" ]]; then
  check_json_endpoint "HTTPS Health" "${PUBLIC_URL}" "/health" 200
fi

echo "Health checks passed."
