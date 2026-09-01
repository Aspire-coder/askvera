# Deployment Checklist

Use this checklist before sending production traffic to ASK Vera.

## AWS And Network

- [ ] EC2 instance is running.
- [ ] EC2 IAM role is attached.
- [ ] Security group allows required inbound traffic.
- [ ] Security group allows outbound AWS service access.
- [ ] DNS `api.vera-api.xyz` points to the API entry point.
- [ ] DNS `chat.vera-api.xyz` points to the widget hosting entry point.
- [ ] SSM parameters are created under `/askverachat/prod/`.
- [ ] Secrets Manager RDS secret is available to the EC2 role.
- [ ] Bedrock Knowledge Base is ready.
- [ ] Bedrock guardrail is published to a numbered version before production.
- [ ] Portal WAF and CloudFront access logging are enabled.
- [ ] GuardDuty Malware Protection is active for the quarantine prefix.
- [ ] GitHub Actions uses OIDC and no long-lived AWS access keys.

## Server Bootstrap

- [ ] `deployment/bootstrap.sh` completed successfully.
- [ ] `/etc/askvera/production.env` reviewed.
- [ ] `/opt/askvera` exists and is owned by `askvera`.
- [ ] Python virtual environment exists at `/opt/askvera/.venv`.
- [ ] Python dependencies installed successfully.

## Runtime

- [ ] `askvera.service` installed.
- [ ] `askvera.service` enabled.
- [ ] `askvera.service` starts successfully.
- [ ] `askvera-ingestion-worker.service` is enabled and healthy.
- [ ] `askvera-retention.timer` is enabled and has a successful last run.
- [ ] `askvera-analytics-reports.timer` is enabled; when reports are enabled, a test aggregate report is delivered.
- [ ] `journalctl -u askvera` shows no startup errors.
- [ ] `/health` returns healthy.
- [ ] `/health/deep` returns healthy.

## Nginx And SSL

- [ ] Nginx config installed.
- [ ] Nginx config test passes.
- [ ] Certbot certificate installed.
- [ ] HTTPS works for `api.vera-api.xyz`.
- [ ] HTTP redirects to HTTPS.
- [ ] Certbot renewal timer is enabled.

## Widget

- [ ] Widget build passes.
- [ ] Widget deployed to static hosting.
- [ ] Widget domain loads.
- [ ] Widget points to the production API URL.
- [ ] Browser CORS checks pass.

## End-To-End Services

- [ ] Bedrock responds through `/api/chat`.
- [ ] Redis cache connects.
- [ ] PostgreSQL session storage works.
- [ ] Consent is recorded in PostgreSQL.
- [ ] Comprehend PII detection works.
- [ ] Firehose audit logging works.
- [ ] SQS feedback enqueue works.
- [ ] A clean upload receives `GuardDutyMalwareScanStatus=NO_THREATS_FOUND` before ingestion.
- [ ] A test upload appears in the correct global or country folder and retrieval scope.

## Release Safety

- [ ] `deployment/deploy.sh` completed successfully.
- [ ] `deployment/healthcheck.sh` passed.
- [ ] `deployment/rollback.sh` tested in a non-production run.
- [ ] GitHub Actions CI passed.
- [ ] npm and Python dependency audits report no known vulnerabilities.
- [ ] Portal and widget production builds contain no source maps.
- [ ] Current deployed commit recorded.
