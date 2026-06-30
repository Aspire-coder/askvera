#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/askvera}"
APP_USER="${APP_USER:-askvera}"
SERVICE_NAME="${SERVICE_NAME:-askvera}"
TARGET_REV="${1:-HEAD~1}"

cd "${APP_DIR}"
echo "Rolling ASK Vera back to ${TARGET_REV}"
sudo -u "${APP_USER}" git fetch --all --tags
sudo -u "${APP_USER}" git checkout "${TARGET_REV}"
systemctl restart "${SERVICE_NAME}"
systemctl status "${SERVICE_NAME}" --no-pager
