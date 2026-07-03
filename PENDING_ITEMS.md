# Pending Items

This file tracks the remaining setup and production-readiness gaps for the ASK Vera chatbot project.

## High Priority

1. Publish the Bedrock guardrail version when ready.
   - Bedrock Knowledge Base ID is configured.
   - Bedrock data source ID is configured.
   - Bedrock model ARN is configured.
   - Bedrock Guardrail ID is configured.
   - Current guardrail version is `DRAFT`.

2. Decide how local startup should work without AWS access.
   - The app currently initializes AWS Secrets Manager and RDS during startup.
   - Local runs require AWS credentials, network access, and permission to read the RDS secret.
   - Consider adding a local/dev fallback or mock mode if local testing is needed without AWS.

3. Move privacy and consent copy out of the route handler.
   - `/api/privacy` currently returns static generic HTML.
   - Privacy, consent, legal links, country-specific text, and language-specific text should come from config or a content source.

4. Confirm AWS Comprehend access for PII detection.
   - Chat requests currently depend on Comprehend PII detection.
   - If Comprehend is unavailable or the IAM role lacks permission, chat can fail before Bedrock is called.

## Application Behavior Items

1. Decide whether blocked or failed chat turns should be stored.
   - Current session history is updated after successful Bedrock responses.
   - Guardrail-blocked or failed turns may not appear in session history.

2. Decide whether database schema creation should remain in startup.
   - Current code creates tables with `CREATE TABLE IF NOT EXISTS`.
   - For production, consider managed migrations such as Alembic.

3. Schedule expired session cleanup.
   - `scripts/cleanup_expired_sessions.py` can delete expired rows.
   - Production still needs a nightly scheduler such as cron, systemd timer, or EventBridge.

4. Add query rewriting and conversation summarization.
   - These are AI quality improvements after the production hardening pass.
   - Query rewriting should remain grounded in user country/language/role.

## Widget Wrapper Items

1. Maintain the production widget delivery path.
   - Current wrapper code lives in `widget-wrapper`.
   - Local demo is wired to the production Python API by default and can be overridden with the `api` query string.
   - Production widget delivery is assigned to `https://chat.vera-api.xyz`.

2. Add the Chatwoot deployment values.
   - Chatwoot base URL.
   - Chatwoot website token.
   - Final decision on hosted Chatwoot versus self-hosted Chatwoot.
   - Final decision on whether to hide Chatwoot's default bubble and use only the generic wrapper launcher.

3. Install wrapper package dependencies before standalone development.
   - The wrapper has its own `package.json`.
   - Run dependency installation in `widget-wrapper` before using its local build scripts.

4. Confirm final wrapper configuration source.
   - Brand text, starter topics, consent copy, legal links, country options, language options, loading text, and success text should come from config.
   - The wrapper implementation should remain generic and reusable.

## Testing And Cleanup

1. Run the full unit test suite after installing project requirements.
   - Python compile checks passed.
   - Config validation passed.
   - Full `pytest` execution still needs to be run in an environment with test dependencies installed.

2. Clean up generated or stale folders before handoff.
   - Review `graphify-out`.
   - Review `tmp`.
   - Review `__pycache__`.
   - Review generated PDF/output folders.

3. Remove leftover generated document artifacts from the outer project area if they are not needed.
   - Some `.docx` files remain under `dist-generic-widget-check/documents`.
   - These were not part of the Python project and should be cleaned up when file permissions allow.

## Completed AWS Values

- AWS account ID is configured as `615592621509`.
- Production CORS origins are configured for `https://chat.vera-api.xyz` and `https://vera-api.xyz`.
- Local widget development CORS origins are configured for `http://127.0.0.1:5174`, `http://localhost:5174`, `http://127.0.0.1:5175`, and `http://localhost:5175`.
- API domain is recorded as `api.vera-api.xyz`.
- Widget domain is recorded as `chat.vera-api.xyz`.

## Completed Production Deployment

- EC2 runtime is provisioned.
- IAM role, security groups, Nginx, systemd, and HTTPS are configured.
- Let's Encrypt SSL is active for `https://api.vera-api.xyz`.
- Porkbun/Cloudflare DNS records are configured for the API and widget domains.
- React widget is connected to the production backend.
- End-to-end widget to FastAPI to Bedrock flow has been verified.

## Completed Hardening Items

- `/api/privacy` now validates country/language values and escapes rendered HTML values.
- `/api/chat` and `/api/consent` now validate supported country/language pairs.
- `/api/chat` now validates the requested role against configured persona roles.
- Comprehend PII scrubbing now uses the request language when supported.
- AWS clients now use explicit timeout and retry configuration.
- PostgreSQL now uses an explicit connection timeout.
- `/health` now reports `draining` after SIGTERM is received.
- `/health/deep` now checks PostgreSQL and Redis and reports AWS dependency configuration.
- Public write endpoints now have a basic in-process rate limiter.
- Bedrock confidence now uses available retrieval/reranker scores and citation quality instead of a binary source check.
- Source citations now include page, document version, country, language, and score when Bedrock metadata provides them.
- Cache keys now include knowledge base, prompt, guardrail, and model versions.
- Expired session cleanup is implemented in `scripts/cleanup_expired_sessions.py`.
