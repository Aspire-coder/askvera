# ASK Vera Deployment

This folder contains repeatable deployment assets for the EC2-hosted FastAPI API.

Production runtime configuration should come from IAM, SSM Parameter Store, and Secrets Manager. Do not place AWS access keys, database passwords, private certificates, or Redis passwords in this folder.

## Files

- `bootstrap.sh` - prepares a fresh Ubuntu EC2 instance.
- `deploy.sh` - pulls the latest code, installs dependencies, validates config, restarts the service, and checks health.
- `rollback.sh` - rolls back to a previous Git revision and restarts the service.
- `healthcheck.sh` - checks `/health` and `/health/deep`.
- `production.env.example` - non-secret runtime environment template.
- `nginx/askvera.conf` - production reverse proxy for `api.vera-api.xyz`.
- `systemd/askvera.service` - systemd unit for Uvicorn.
- `ssl/certbot.sh` - Certbot automation for the API domain.

## First-Time EC2 Setup

```bash
chmod +x deployment/*.sh deployment/ssl/*.sh
sudo REPO_URL=https://github.com/Aspire-coder/askvera.git ./deployment/bootstrap.sh
sudo EMAIL=you@example.com ./deployment/ssl/certbot.sh
sudo ./deployment/deploy.sh
```

`bootstrap.sh` does not enable the HTTPS Nginx site because the certificate does not exist yet. `ssl/certbot.sh` installs a temporary HTTP proxy, obtains the certificate, then installs the production HTTPS config.

## Normal Deploy

```bash
sudo ./deployment/deploy.sh
```

## Service Operations

```bash
sudo systemctl status askvera --no-pager
sudo systemctl restart askvera
sudo journalctl -u askvera -f
```

## Nginx Operations

```bash
sudo nginx -t
sudo systemctl reload nginx
sudo tail -f /var/log/nginx/access.log /var/log/nginx/error.log
```

## Rollback

```bash
sudo ./deployment/rollback.sh HEAD~1
```

## Widget Deployment

The widget should be built and deployed separately to static hosting such as S3 plus CloudFront for `chat.vera-api.xyz`.

```bash
cd widget-wrapper
npm ci
npm run build:demo
```
