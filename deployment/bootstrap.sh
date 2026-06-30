#!/usr/bin/env bash
set -euo pipefail

APP_USER="${APP_USER:-askvera}"
APP_DIR="${APP_DIR:-/opt/askvera}"
REPO_URL="${REPO_URL:-https://github.com/Aspire-coder/askvera.git}"
ENV_DIR="${ENV_DIR:-/etc/askvera}"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run bootstrap.sh as root." >&2
  exit 1
fi

apt-get update
apt-get install -y \
  build-essential \
  curl \
  git \
  nginx \
  certbot \
  python3-certbot-nginx \
  python3.11 \
  python3.11-dev \
  python3.11-venv \
  python3-pip

if ! id "${APP_USER}" >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin "${APP_USER}"
fi

mkdir -p "${APP_DIR}" "${ENV_DIR}"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

if [[ ! -d "${APP_DIR}/.git" ]]; then
  sudo -u "${APP_USER}" git clone "${REPO_URL}" "${APP_DIR}"
else
  sudo -u "${APP_USER}" git -C "${APP_DIR}" fetch origin main
fi

if [[ ! -f "${ENV_DIR}/production.env" ]]; then
  cp "${APP_DIR}/deployment/production.env.example" "${ENV_DIR}/production.env"
  chmod 0640 "${ENV_DIR}/production.env"
  chown root:"${APP_USER}" "${ENV_DIR}/production.env"
fi

cp "${APP_DIR}/deployment/systemd/askvera.service" /etc/systemd/system/askvera.service

sudo -u "${APP_USER}" "${PYTHON_BIN}" -m venv "${APP_DIR}/.venv"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m pip install --upgrade pip
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m pip install -r "${APP_DIR}/requirements.txt"

systemctl daemon-reload
systemctl enable askvera

echo "Bootstrap complete. Review ${ENV_DIR}/production.env, run deployment/ssl/certbot.sh, then run deployment/deploy.sh."
