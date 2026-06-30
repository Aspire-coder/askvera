#!/usr/bin/env bash
set -euo pipefail

APP_USER="${APP_USER:-askvera}"
APP_DIR="${APP_DIR:-/opt/askvera}"
REPO_URL="${REPO_URL:-https://github.com/Aspire-coder/askvera.git}"
ENV_DIR="${ENV_DIR:-/etc/askvera}"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"
BRANCH="${BRANCH:-main}"
PKG_MANAGER=""

log() {
  echo "[bootstrap] $*"
}

detect_package_manager() {
  if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release
    case "${ID:-}" in
      ubuntu|debian)
        PKG_MANAGER="apt"
        return
        ;;
      amzn|amazon)
        PKG_MANAGER="dnf"
        return
        ;;
    esac

    case "${ID_LIKE:-}" in
      *debian*)
        PKG_MANAGER="apt"
        return
        ;;
      *fedora*|*rhel*)
        PKG_MANAGER="dnf"
        return
        ;;
    esac
  fi

  if command -v apt-get >/dev/null 2>&1; then
    PKG_MANAGER="apt"
  elif command -v dnf >/dev/null 2>&1; then
    PKG_MANAGER="dnf"
  else
    echo "Unsupported OS: expected Ubuntu/Debian with apt or Amazon Linux with dnf." >&2
    exit 1
  fi
}

install_system_packages() {
  case "${PKG_MANAGER}" in
    apt)
      export DEBIAN_FRONTEND=noninteractive
      apt-get update
      apt-get install -y \
        ca-certificates \
        software-properties-common \
        build-essential \
        curl \
        git \
        sudo \
        nginx \
        certbot \
        python3-certbot-nginx \
        python3.11 \
        python3.11-dev \
        python3.11-venv \
        python3-pip
      ;;
    dnf)
      dnf_packages=(
        ca-certificates
        gcc
        gcc-c++
        make
        git
        sudo
        nginx
        certbot
        python3-certbot-nginx
        python3.11
        python3.11-devel
        python3.11-pip
      )
      if ! command -v curl >/dev/null 2>&1; then
        dnf_packages+=(curl-minimal)
      fi
      dnf install -y "${dnf_packages[@]}"
      ;;
    *)
      echo "Unsupported package manager: ${PKG_MANAGER}" >&2
      exit 1
      ;;
  esac
}

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run bootstrap.sh as root." >&2
  exit 1
fi

detect_package_manager
log "Installing system packages with ${PKG_MANAGER}."
install_system_packages

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "${PYTHON_BIN} is not available after package installation." >&2
  echo "On older Ubuntu releases, install Python 3.11 or set PYTHON_BIN to the available interpreter." >&2
  exit 1
fi

if ! id "${APP_USER}" >/dev/null 2>&1; then
  NOLOGIN_SHELL="$(command -v nologin || echo /sbin/nologin)"
  log "Creating service user ${APP_USER}."
  useradd --system --create-home --shell "${NOLOGIN_SHELL}" "${APP_USER}"
fi

mkdir -p "${APP_DIR}" "${ENV_DIR}"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

if [[ ! -d "${APP_DIR}/.git" ]]; then
  if [[ -n "$(find "${APP_DIR}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    echo "${APP_DIR} exists and is not empty, but it is not a Git repository." >&2
    exit 1
  fi
  log "Cloning ${REPO_URL} into ${APP_DIR}."
  sudo -u "${APP_USER}" git clone --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
else
  log "Refreshing existing repository."
  sudo -u "${APP_USER}" git -C "${APP_DIR}" fetch origin "${BRANCH}"
fi

if [[ ! -f "${ENV_DIR}/production.env" ]]; then
  log "Creating ${ENV_DIR}/production.env from template."
  cp "${APP_DIR}/deployment/production.env.example" "${ENV_DIR}/production.env"
  chmod 0640 "${ENV_DIR}/production.env"
  chown root:"${APP_USER}" "${ENV_DIR}/production.env"
else
  log "Keeping existing ${ENV_DIR}/production.env."
fi

log "Installing systemd service."
cp "${APP_DIR}/deployment/systemd/askvera.service" /etc/systemd/system/askvera.service

log "Creating/updating Python virtual environment."
sudo -u "${APP_USER}" "${PYTHON_BIN}" -m venv "${APP_DIR}/.venv"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m pip install --upgrade pip
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m pip install -r "${APP_DIR}/requirements.txt"

log "Enabling systemd service."
systemctl daemon-reload
systemctl enable askvera

log "Validating Python package import and application config."
cd "${APP_DIR}"
set -a
source "${ENV_DIR}/production.env"
set +a
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m compileall api config services utils scripts >/dev/null
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" scripts/validate_config.py

echo "Bootstrap complete. Review ${ENV_DIR}/production.env, run deployment/ssl/certbot.sh, then run deployment/deploy.sh."
