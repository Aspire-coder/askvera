# AskVera Production Hardening

This document records the production safeguards around retrieval, generation,
caching, sessions, and support escalation. It separates implemented behavior
from infrastructure decisions that require approval.

## Implemented

### Cache freshness

- Answer cache keys include the cache schema, knowledge-base, retrieval
  pipeline, prompt, guardrail, primary-model, and fallback-model versions.
- Approved OpenSearch publication can rotate `KB_VERSION` only after the new
  active records are indexed and older copies are removed successfully.
- Restarting the API after publication loads the new SSM version and makes old
  cache entries unreachable without deleting them during live traffic.

### Validation failures

- Answers pass citation, numeric-grounding, PII, and output-governance checks.
- Repairable output gets one controlled repair attempt.
- A failed repair returns a safe fallback with a `failureLayer`; an unvalidated
  answer is never returned to the widget.

### Retrieval precision

- Retrieval combines keyword and vector evidence with strict market/language
  filters and globally scoped documents where permitted.
- The optional evidence selector reranks retrieved evidence before generation.
- Any change to retrieval or reranking must pass the locale evaluation set
  before its version is promoted.

### Model resilience

- Transient Bedrock failures can use a separately configured fallback model.
- Repeated transient primary-model failures open a short process-local circuit
  breaker so requests do not repeatedly wait on an unhealthy model.
- Authentication, authorization, validation, and other non-transient failures
  do not fail over and remain visible as real operational errors.

### Session lifecycle

- Widget tokens expire and can be refreshed.
- Sessions enforce idle and absolute lifetime limits.
- Session resumption is bound to the originating widget instance and approved
  website origin. A session identifier alone cannot resume a conversation.
- New chat and end chat explicitly close the prior conversation state.

### Operational transcript controls

- Analytics persistence scrubs common PII from questions, answers, feedback,
  and suggested answers before storage.
- The hardened profile requires redacted, bounded interaction previews by
  default. Raw interaction access is a separate disabled-by-default setting,
  restricted through the Audit permission and recorded in `admin_audit_log`.

### Ingestion safety

- Hardened preflight validates the claimed file type before parsing and applies
  PDF page, extracted-text, and parser-time limits in an isolated subprocess.
- Malware scanning, queue delivery, staged publication, and OCR remain
  separately gated until their AWS resources and permissions are approved.

### Human support

- Users can request support manually from the widget menu.
- The widget recommends support after a configurable number of consecutive
  failed answers; one isolated fallback does not immediately interrupt a user.
- Negative feedback can also expose the support action.

### Rollback controls

- Prompt, retrieval, knowledge, guardrail, and model settings are versioned.
- Git deployment rollback is supported by `deployment/rollback.sh`.
- SSM values used for a release must be recorded with the release so application
  and runtime configuration can be rolled back together.

## Approval Required

### Edge protection

AWS WAF cannot be attached directly to the current Nginx process on EC2. Add an
approved edge layer, preferably CloudFront or an Application Load Balancer, then
attach WAF managed rules and a rate-based rule there. Keep FastAPI rate limits as
defense in depth. Do not expose an alternate path that bypasses the edge layer.

### Data residency

The current application data plane is in `us-east-1`. Before broader production
rollout, Privacy and Legal must decide whether EU and other markets may store
consent, chat, audit, and support data there. If not, deploy regional data planes
and route each market to its approved region; do not solve residency with only a
country metadata field.

### Conversation hot cache

Conversation history is deliberately bounded before it is read from RDS. Add a
Valkey hot-session layer only if production latency and database metrics show it
is needed. Introducing a second source of session truth without evidence would
increase consistency and privacy risk.

## Release Gate

Before production promotion:

1. Run unit tests and the widget production build.
2. Run retrieval evaluation for every affected market and language.
3. Publish documents as staging and verify counts, metadata, and isolation.
4. Publish active records with replacement and rotate `KB_VERSION`.
5. Record Git commit and SSM runtime versions in the release entry.
6. Run `scripts/validate_config.py --load-ssm` before restart and correct any
   reported configuration issue while the current service is still running.
7. Restart the API, run health checks, and execute representative live tests.
8. Confirm dashboards show no rise in fallbacks, validation failures, or model
   failover before completing the rollout.

## Deployment Authentication

- GitHub Actions assumes a least-privilege AWS role using OpenID Connect and
  the repository secret `AWS_DEPLOY_ROLE_ARN`.
- Do not store long-lived AWS access keys in repository or environment secrets.
- Validate SSM with `scripts/validate_config.py --load-ssm
  --require-production` before restarting the running production service.
- Production and hardened configurations reject unknown SSM names, malformed
  booleans, and the mutable `DRAFT` Bedrock Guardrail version.
- Use public `GET /health` for uptime checks. `GET /health/deep` is restricted
  to authenticated administrators.
- Operations portal production builds omit source maps.
