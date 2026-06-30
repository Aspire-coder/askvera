#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${DOMAIN:-api.vera-api.xyz}"
EMAIL="${EMAIL:?Set EMAIL before running certbot.sh}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run certbot.sh as root." >&2
  exit 1
fi

apt-get update
apt-get install -y certbot python3-certbot-nginx

cp /opt/askvera/deployment/nginx/askvera.conf /etc/nginx/sites-available/askvera.conf
ln -sfn /etc/nginx/sites-available/askvera.conf /etc/nginx/sites-enabled/askvera.conf
rm -f /etc/nginx/sites-enabled/default

if [[ ! -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
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
systemctl reload nginx
certbot --nginx --non-interactive --agree-tos --redirect --email "${EMAIL}" -d "${DOMAIN}"
cp /opt/askvera/deployment/nginx/askvera.conf /etc/nginx/sites-available/askvera.conf
nginx -t
systemctl enable certbot.timer
systemctl reload nginx

echo "Certificate installed for ${DOMAIN}."
