#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/askvera}"
APP_USER="${APP_USER:-askvera}"
SERVICE_NAME="${SERVICE_NAME:-askvera}"
HEALTH_BASE_URL="${HEALTH_BASE_URL:-https://api.vera-api.xyz}"
TARGET_REV="${1:-HEAD~1}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run rollback.sh as root." >&2
  exit 1
fi

cd "${APP_DIR}"
echo "Rolling ASK Vera back to ${TARGET_REV}"

if ! sudo -u "${APP_USER}" git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "${APP_DIR} is not a Git repository." >&2
  exit 1
fi

sudo -u "${APP_USER}" git fetch --all --tags

if ! RESOLVED_REV="$(sudo -u "${APP_USER}" git rev-parse --verify "${TARGET_REV}^{commit}")"; then
  echo "Rollback target does not exist: ${TARGET_REV}" >&2
  exit 1
fi
CURRENT_REV="$(sudo -u "${APP_USER}" git rev-parse HEAD)"

echo "Current commit: ${CURRENT_REV}"
echo "Target commit: ${RESOLVED_REV}"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "${APP_DIR}/.venv is missing or incomplete. Run bootstrap.sh first." >&2
  exit 1
fi

sudo -u "${APP_USER}" git checkout "${RESOLVED_REV}"
sudo -u "${APP_USER}" .venv/bin/python -m pip install -r requirements.txt
systemctl restart "${SERVICE_NAME}"
sleep 3

if ! PUBLIC_URL="${HEALTH_BASE_URL}" "${APP_DIR}/deployment/healthcheck.sh"; then
  echo "Rollback health check failed. Service may be unhealthy at ${RESOLVED_REV}." >&2
  exit 1
fi

systemctl status "${SERVICE_NAME}" --no-pager
echo "Rollback complete: ${RESOLVED_REV}"
