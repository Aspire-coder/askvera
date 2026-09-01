#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/askvera}"
APP_USER="${APP_USER:-askvera}"
SERVICE_NAME="${SERVICE_NAME:-askvera}"
HEALTH_BASE_URL="${HEALTH_BASE_URL:-https://api.vera-api.xyz}"
RUN_TESTS="${RUN_TESTS:-true}"
BRANCH="${BRANCH:-main}"
STARTUP_HEALTH_ATTEMPTS="${STARTUP_HEALTH_ATTEMPTS:-15}"
STARTUP_HEALTH_INTERVAL_SECONDS="${STARTUP_HEALTH_INTERVAL_SECONDS:-2}"

usage() {
  cat <<USAGE
Usage: sudo ./deployment/deploy.sh [--skip-tests]

Environment overrides:
  APP_DIR=/opt/askvera
  APP_USER=askvera
  SERVICE_NAME=askvera
  HEALTH_BASE_URL=https://api.vera-api.xyz
  BRANCH=main
  STARTUP_HEALTH_ATTEMPTS=15
  STARTUP_HEALTH_INTERVAL_SECONDS=2
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

wait_for_local_health() {
  local attempt
  local local_health_url="http://127.0.0.1:8000/health"

  for ((attempt = 1; attempt <= STARTUP_HEALTH_ATTEMPTS; attempt++)); do
    if curl --silent --show-error --fail --max-time 5 "${local_health_url}" >/dev/null; then
      log "Service became ready on attempt ${attempt}."
      return 0
    fi

    if ((attempt < STARTUP_HEALTH_ATTEMPTS)); then
      sleep "${STARTUP_HEALTH_INTERVAL_SECONDS}"
    fi
  done

  echo "Service did not become ready after ${STARTUP_HEALTH_ATTEMPTS} attempts." >&2
  return 1
}

rollback() {
  local previous_rev="$1"
  if [[ -n "${previous_rev}" ]]; then
    echo "Rolling back to ${previous_rev}" >&2
    sudo -u "${APP_USER}" git -C "${APP_DIR}" checkout "${previous_rev}"
    systemctl restart "${SERVICE_NAME}"
    if wait_for_local_health; then
      PUBLIC_URL="${HEALTH_BASE_URL}" bash "${APP_DIR}/deployment/healthcheck.sh" || true
    fi
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
sudo -u "${APP_USER}" .venv/bin/python -m compileall app api config services utils scripts tests >/dev/null

log "Validating production configuration before restart."
sudo -u "${APP_USER}" .venv/bin/python scripts/validate_config.py --load-ssm --require-production

log "Checking database migrations."
sudo -u "${APP_USER}" .venv/bin/python scripts/run_db_migrations.py --load-ssm

if [[ "${RUN_TESTS}" == "true" ]]; then
  log "Running tests."
  sudo -u "${APP_USER}" .venv/bin/python -m pytest tests -q
else
  log "Skipping tests by explicit request."
fi

log "Applying database migrations."
sudo -u "${APP_USER}" .venv/bin/python scripts/run_db_migrations.py --load-ssm --apply

log "Restarting ${SERVICE_NAME} and ingestion worker."
systemctl restart "${SERVICE_NAME}"
systemctl restart askvera-ingestion-worker

log "Running health checks."
if ! wait_for_local_health ||
  ! PUBLIC_URL="${HEALTH_BASE_URL}" bash "${APP_DIR}/deployment/healthcheck.sh"; then
  echo "Health check failed after deploy." >&2
  rollback "${PREVIOUS_REV}"
  exit 1
fi

DEPLOYED_REV="$(sudo -u "${APP_USER}" git rev-parse --short HEAD)"
echo "Deployment complete. Deployed commit: ${DEPLOYED_REV}"
