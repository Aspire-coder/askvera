#!/usr/bin/env bash
set -Eeuo pipefail

DOMAIN="${DOMAIN:-api.vera-api.xyz}"
EMAIL="${EMAIL:?Set EMAIL before running certbot.sh}"
APP_DIR="${APP_DIR:-/opt/askvera}"
CURL_TIMEOUT_SECONDS="${CURL_TIMEOUT_SECONDS:-5}"

log() {
  echo "[certbot] $*"
}

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run certbot.sh as root." >&2
  exit 1
fi

if ! getent hosts "${DOMAIN}" >/dev/null; then
  echo "${DOMAIN} does not resolve. Fix DNS before requesting a certificate." >&2
  exit 1
fi

log "Installing Certbot packages if needed."
if ! dpkg -s certbot python3-certbot-nginx openssl >/dev/null 2>&1; then
  apt-get update
  apt-get install -y certbot python3-certbot-nginx openssl
fi

cp "${APP_DIR}/deployment/nginx/askvera.conf" /etc/nginx/sites-available/askvera.conf
ln -sfn /etc/nginx/sites-available/askvera.conf /etc/nginx/sites-enabled/askvera.conf
rm -f /etc/nginx/sites-enabled/default

if [[ ! -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
  log "Installing temporary HTTP Nginx config."
  cat >/etc/nginx/sites-available/askvera.conf <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \\$host;
        proxy_set_header X-Real-IP \\$remote_addr;
        proxy_set_header X-Forwarded-For \\$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \\$scheme;
    }
}
NGINX
fi

nginx -t
systemctl reload nginx || systemctl restart nginx

if ! curl --silent --show-error --max-time "${CURL_TIMEOUT_SECONDS}" "http://${DOMAIN}/health" >/dev/null; then
  echo "HTTP health check failed for ${DOMAIN}. Verify port 80 is open and Nginx can reach FastAPI." >&2
  exit 1
fi

log "Requesting certificate for ${DOMAIN}."
certbot --nginx --non-interactive --agree-tos --redirect --email "${EMAIL}" -d "${DOMAIN}"

if [[ ! -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
  echo "Certificate file was not created for ${DOMAIN}." >&2
  exit 1
fi

openssl x509 -in "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" -noout -subject -issuer -dates

log "Installing production HTTPS Nginx config."
cp "${APP_DIR}/deployment/nginx/askvera.conf" /etc/nginx/sites-available/askvera.conf
nginx -t
systemctl enable certbot.timer
systemctl reload nginx

if ! curl --silent --show-error --fail --max-time "${CURL_TIMEOUT_SECONDS}" "https://${DOMAIN}/health" >/dev/null; then
  echo "HTTPS health check failed for ${DOMAIN} after certificate installation." >&2
  exit 1
fi

echo "Certificate installed for ${DOMAIN}."
