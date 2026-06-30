#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/askvera}"
APP_USER="${APP_USER:-askvera}"
SERVICE_NAME="${SERVICE_NAME:-askvera}"
HEALTH_BASE_URL="${HEALTH_BASE_URL:-https://api.vera-api.xyz}"
RUN_TESTS="${RUN_TESTS:-true}"
PREVIOUS_REV="$(sudo -u "${APP_USER}" git -C "${APP_DIR}" rev-parse HEAD 2>/dev/null || true)"

echo "Deploying ASK Vera from ${APP_DIR}"
cd "${APP_DIR}"

sudo -u "${APP_USER}" git fetch origin main
sudo -u "${APP_USER}" git checkout main
sudo -u "${APP_USER}" git pull --ff-only origin main

sudo -u "${APP_USER}" .venv/bin/python -m pip install --upgrade pip
sudo -u "${APP_USER}" .venv/bin/python -m pip install -r requirements.txt

if [[ "${RUN_TESTS}" == "true" ]]; then
  sudo -u "${APP_USER}" .venv/bin/python -m pytest tests/unit -q
fi

sudo -u "${APP_USER}" .venv/bin/python scripts/validate_config.py

systemctl restart "${SERVICE_NAME}"
sleep 3

if ! BASE_URL="${HEALTH_BASE_URL}" "${APP_DIR}/deployment/healthcheck.sh"; then
  echo "Health check failed after deploy." >&2
  if [[ -n "${PREVIOUS_REV}" ]]; then
    echo "Rolling back to ${PREVIOUS_REV}" >&2
    sudo -u "${APP_USER}" git checkout "${PREVIOUS_REV}"
    systemctl restart "${SERVICE_NAME}"
    BASE_URL="${HEALTH_BASE_URL}" "${APP_DIR}/deployment/healthcheck.sh" || true
  fi
  exit 1
fi

echo "Deployment complete."
