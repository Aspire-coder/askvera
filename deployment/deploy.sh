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
    # A refused connection while the service is still starting is expected, so
    # an attempt's own error is discarded. Printing it made every deploy show
    # two "curl: (7) Failed to connect" lines that look like failures and are
    # not. Only the final attempt keeps its stderr, so a genuine timeout still
    # shows why it failed rather than only that it did.
    #
    # Both branches stay inside an "if" condition on purpose: under the
    # "set -e" at the top of this script, a bare failing command here would
    # abort the function before the summary below could report the timeout.
    if ((attempt == STARTUP_HEALTH_ATTEMPTS)); then
      if curl --silent --show-error --fail --max-time 5 "${local_health_url}" >/dev/null; then
        log "Service became ready on attempt ${attempt}."
        return 0
      fi
    elif curl --silent --fail --max-time 5 "${local_health_url}" >/dev/null 2>&1; then
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

run_retrieval_canary() {
  log "Running blocking retrieval-quality canary against the active index."
  sudo -u "${APP_USER}" .venv/bin/python scripts/run_retrieval_canary.py --load-ssm
}

sync_runtime_configuration() {
  log "Applying checked-in systemd and Nginx configuration."
  install -m 0644 deployment/systemd/askvera.service /etc/systemd/system/askvera.service
  install -m 0644 deployment/systemd/askvera-ingestion-worker.service /etc/systemd/system/askvera-ingestion-worker.service
  install -m 0644 deployment/systemd/askvera-retention.service /etc/systemd/system/askvera-retention.service
  install -m 0644 deployment/systemd/askvera-retention.timer /etc/systemd/system/askvera-retention.timer
  install -m 0644 deployment/systemd/askvera-analytics-reports.service /etc/systemd/system/askvera-analytics-reports.service
  install -m 0644 deployment/systemd/askvera-analytics-reports.timer /etc/systemd/system/askvera-analytics-reports.timer

  if [[ -d /etc/nginx/conf.d ]]; then
    install -m 0644 deployment/nginx/askvera.conf /etc/nginx/conf.d/askvera.conf
  elif [[ -d /etc/nginx/sites-available ]]; then
    install -m 0644 deployment/nginx/askvera.conf /etc/nginx/sites-available/askvera.conf
    ln -sfn /etc/nginx/sites-available/askvera.conf /etc/nginx/sites-enabled/askvera.conf
  else
    echo "No supported Nginx configuration directory was found." >&2
    return 1
  fi

  nginx -t
  systemctl daemon-reload
  systemctl enable askvera-retention.timer
  systemctl restart askvera-retention.timer
  systemctl enable askvera-analytics-reports.timer
  systemctl restart askvera-analytics-reports.timer
  if sudo -u "${APP_USER}" .venv/bin/python -c \
    'from config import settings; settings.load_ssm_config(); raise SystemExit(0 if settings.ADMIN_INGESTION_QUEUE_ENABLED else 1)'; then
    systemctl enable askvera-ingestion-worker.service
    systemctl restart askvera-ingestion-worker.service
  else
    log "Durable ingestion queueing is disabled; keeping the worker stopped."
    systemctl disable --now askvera-ingestion-worker.service || true
  fi
  systemctl reload nginx
}

rollback() {
  local previous_rev="$1"
  if [[ -n "${previous_rev}" ]]; then
    echo "Rolling back to ${previous_rev}" >&2
    sudo -u "${APP_USER}" git -C "${APP_DIR}" checkout "${previous_rev}"
    sync_runtime_configuration || true
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

# Everything from here is copied to a timestamped file as well as the terminal.
#
# Until now a deploy's output existed only in whoever ran it's scrollback, so
# the retrieval canary's per-case scores, the health timings and any rollback
# were unrecoverable once that window closed. On 2026-09-07 a question about
# what grounding repair had removed from a delivered answer could not be
# answered for exactly this reason.
#
# Started after the root check so a non-root run does not create a root-owned
# log directory as its only effect. `tee` keeps the terminal behaviour
# identical, and PIPESTATUS is preserved because the redirect happens through
# process substitution rather than a pipeline, so `set -e` still sees the
# script's own exit status rather than tee's.
DEPLOY_LOG_DIR="${DEPLOY_LOG_DIR:-/var/log/askvera}"
if mkdir -p "${DEPLOY_LOG_DIR}" 2>/dev/null; then
  DEPLOY_LOG_FILE="${DEPLOY_LOG_DIR}/deploy-$(date -u +%Y%m%dT%H%M%SZ).log"
  exec > >(tee -a "${DEPLOY_LOG_FILE}") 2>&1
  echo "[deploy] Recording this deploy to ${DEPLOY_LOG_FILE}"
  # Keep a bounded history rather than growing without limit. Deploys are
  # infrequent and these files are small, so the cap is generous.
  # tail -n +N starts at line N, so keeping N files means starting at N+1.
  DEPLOY_LOG_KEEP="${DEPLOY_LOG_KEEP:-50}"
  ls -1t "${DEPLOY_LOG_DIR}"/deploy-*.log 2>/dev/null \
    | tail -n +"$((DEPLOY_LOG_KEEP + 1))" \
    | xargs -r rm -f
else
  echo "[deploy] Could not write to ${DEPLOY_LOG_DIR}; continuing without a deploy log." >&2
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

log "Applying ordered database migrations."
sudo -u "${APP_USER}" .venv/bin/python scripts/run_db_migrations.py --load-ssm --apply

if [[ "${RUN_TESTS}" == "true" ]]; then
  log "Running tests."
  sudo -u "${APP_USER}" .venv/bin/python -m pytest tests -q
else
  log "Skipping tests by explicit request."
fi

sync_runtime_configuration

log "Restarting ${SERVICE_NAME}."
systemctl restart "${SERVICE_NAME}"

log "Running health checks."
if ! wait_for_local_health ||
  ! PUBLIC_URL="${HEALTH_BASE_URL}" bash "${APP_DIR}/deployment/healthcheck.sh" ||
  ! run_retrieval_canary; then
  echo "Health or retrieval-quality check failed after deploy." >&2
  rollback "${PREVIOUS_REV}"
  exit 1
fi

DEPLOYED_REV="$(sudo -u "${APP_USER}" git rev-parse --short HEAD)"
echo "Deployment complete. Deployed commit: ${DEPLOYED_REV}"
