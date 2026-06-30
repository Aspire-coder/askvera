#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/askvera}"
APP_USER="${APP_USER:-askvera}"
SERVICE_NAME="${SERVICE_NAME:-askvera}"
HEALTH_BASE_URL="${HEALTH_BASE_URL:-https://api.vera-api.xyz}"
RUN_TESTS="${RUN_TESTS:-true}"
BRANCH="${BRANCH:-main}"

usage() {
  cat <<USAGE
Usage: sudo ./deployment/deploy.sh [--skip-tests]

Environment overrides:
  APP_DIR=/opt/askvera
  APP_USER=askvera
  SERVICE_NAME=askvera
  HEALTH_BASE_URL=https://api.vera-api.xyz
  BRANCH=main
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-tests)
      RUN_TESTS=false
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

log() {
  echo "[deploy] $*"
}

rollback() {
  local previous_rev="$1"
  if [[ -n "${previous_rev}" ]]; then
    echo "Rolling back to ${previous_rev}" >&2
    sudo -u "${APP_USER}" git -C "${APP_DIR}" checkout "${previous_rev}"
    systemctl restart "${SERVICE_NAME}"
    sleep 3
    PUBLIC_URL="${HEALTH_BASE_URL}" "${APP_DIR}/deployment/healthcheck.sh" || true
  fi
}

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run deploy.sh as root." >&2
  exit 1
fi

log "Deploying ASK Vera from ${APP_DIR}"
cd "${APP_DIR}"

if ! sudo -u "${APP_USER}" git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "${APP_DIR} is not a Git repository. Run bootstrap.sh first." >&2
  exit 1
fi

if [[ ! -x ".venv/bin/python" ]]; then
  echo "${APP_DIR}/.venv is missing or incomplete. Run bootstrap.sh first." >&2
  exit 1
fi

PREVIOUS_REV="$(sudo -u "${APP_USER}" git rev-parse HEAD)"

log "Fetching latest ${BRANCH}."
sudo -u "${APP_USER}" git fetch origin "${BRANCH}"
sudo -u "${APP_USER}" git checkout "${BRANCH}"
sudo -u "${APP_USER}" git pull --ff-only origin "${BRANCH}"

log "Installing Python dependencies."
sudo -u "${APP_USER}" .venv/bin/python -m pip install --upgrade pip
sudo -u "${APP_USER}" .venv/bin/python -m pip install -r requirements.txt

log "Compiling Python source."
sudo -u "${APP_USER}" .venv/bin/python -m compileall api config services utils scripts tests >/dev/null

log "Validating configuration."
sudo -u "${APP_USER}" .venv/bin/python scripts/validate_config.py

if [[ "${RUN_TESTS}" == "true" ]]; then
  log "Running tests."
  sudo -u "${APP_USER}" .venv/bin/python -m pytest tests -q
else
  log "Skipping tests by explicit request."
fi

log "Restarting ${SERVICE_NAME}."
systemctl restart "${SERVICE_NAME}"
sleep 3

log "Running health checks."
if ! PUBLIC_URL="${HEALTH_BASE_URL}" "${APP_DIR}/deployment/healthcheck.sh"; then
  echo "Health check failed after deploy." >&2
  rollback "${PREVIOUS_REV}"
  exit 1
fi

DEPLOYED_REV="$(sudo -u "${APP_USER}" git rev-parse --short HEAD)"
echo "Deployment complete. Deployed commit: ${DEPLOYED_REV}"
