#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/askvera}"
APP_USER="${APP_USER:-askvera}"
SERVICE_NAME="${SERVICE_NAME:-askvera}"
HEALTH_BASE_URL="${HEALTH_BASE_URL:-https://api.vera-api.xyz}"
TARGET_REV="${1:-HEAD~1}"

cd "${APP_DIR}"
echo "Rolling ASK Vera back to ${TARGET_REV}"
sudo -u "${APP_USER}" git fetch --all --tags
sudo -u "${APP_USER}" git checkout "${TARGET_REV}"
sudo -u "${APP_USER}" .venv/bin/python -m pip install -r requirements.txt
systemctl restart "${SERVICE_NAME}"
sleep 3
BASE_URL="${HEALTH_BASE_URL}" "${APP_DIR}/deployment/healthcheck.sh"
systemctl status "${SERVICE_NAME}" --no-pager
