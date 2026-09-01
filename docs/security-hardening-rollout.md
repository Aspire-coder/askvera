# AskVera Security and Ingestion Hardening Rollout

## Purpose

This package strengthens document ingestion, legal-content rendering, browser
privacy, administrator access, and operational-data retention. It does not
change the active retrieval provider, retrieval index, ranking, prompts, or
answer-generation model.

All higher-risk runtime changes are disabled by default. Deploy the code first,
then enable each capability separately after its checks pass.

## What Changes Immediately

- Legal HTML is sanitized on the API and again in the widget.
- Legal-document printing no longer uses `document.write`.
- Query-planner output is bounded and schema-checked.
- Full browser transcripts use `sessionStorage` by default instead of
  `localStorage`. Closing the browser tab removes that browser copy.
- Retention settings become available, but no deletion occurs until the timer is
  installed and started.

## What Remains Off

| Setting | Default | Effect when enabled |
| --- | --- | --- |
| `ADMIN_INGESTION_QUEUE_ENABLED` | `false` | Stores accepted uploads in private S3 and sends a compact SQS command. |
| `ADMIN_INGESTION_STAGED_PUBLISH_ENABLED` | `false` | Verifies a complete OpenSearch generation before activation. |
| `ADMIN_INGESTION_GENERATION_POINTER_ENABLED` | `false` | Makes retrieval use only the active generation selected in RDS. |
| `ADMIN_INGESTION_APPROVAL_METADATA_REQUIRED` | `false` | Requires a stable document ID, owner, approval reference, and effective date. |
| `ADMIN_INGESTION_MALWARE_SCAN_REQUIRED` | `false` | Prevents workers from opening an upload until its malware-scan tag is clean. |
| `ADMIN_TEXTRACT_OCR_ENABLED` | `false` | Uses Textract for scanned PDFs that fail text preflight. |
| `ADMIN_ANALYTICS_REDACTED_BY_DEFAULT` | `false` | Returns PII-scrubbed, length-bounded interaction previews from the portal API. Required by the hardened profile. |
| `ADMIN_ANALYTICS_RAW_TRANSCRIPT_ACCESS_ENABLED` | `false` | Permits a separately authorized and audited raw interaction view. Leave disabled unless Privacy approves the operational need. |
| `SECURITY_PROFILE` | `standard` | `hardened` makes required security controls fail closed at startup. |
| `EnableWebAcl` | `false` | Attaches AWS managed WAF protections to the operations portal. |

## Safe Deployment Sequence

### 1. Validate Runtime Configuration Before Restart

Populate the proposed SSM values first, but do not restart the API yet. Run the
same validation used during startup against SSM and resolve every reported
missing or malformed value before changing the running service:

```bash
cd /opt/askvera
sudo -u askvera env PYTHONDONTWRITEBYTECODE=1 \
  /opt/askvera/.venv/bin/python -B scripts/validate_config.py --load-ssm
```

This is a dry run. It prevents a typo in an ARN, queue URL, or hardened flag
from becoming an avoidable restart outage.

Boolean SSM values are parsed strictly. Ambiguous values such as `enabled`,
`disabled`, or a misspelling are rejected. The full SSM batch is validated
before any value is applied, so one malformed parameter cannot leave the
process with a partially updated configuration. Production and hardened
profiles also reject unknown parameter names; remove stale or misspelled
parameters before restarting.

### 2. Deploy Code With Defaults

Deploy the API and widget code with every setting above left at its default.
Run health checks and the current retrieval regression suite. Existing uploads
continue to use the current in-process background task.

Rollback: deploy the previous Git revision. No infrastructure or data path has
changed yet.

### 3. Apply Database Migrations

Dry-run and apply the ordered migrations. They add ingestion ownership,
approval, effective-date, retry-state, active-generation, and generation-history
records without replacing existing tables. Verify existing jobs and documents
remain unchanged.

Rollback: leave the additive columns in place. They are ignored while queueing
is disabled.

### 4. Create Queue Infrastructure

Deploy `deployment/ingestion-queue.yaml` as a CloudFormation change set. Review
the encrypted main queue, retained dead-letter queue, message-age alarm, and
dead-letter alarm before execution.

Set `ADMIN_INGESTION_QUEUE_URL` and `ADMIN_INGESTION_DLQ_URL` to the stack
outputs, but keep
`ADMIN_INGESTION_QUEUE_ENABLED=false`.

Rollback: do not delete retained queues until operators confirm they are empty.

### 5. Grant Least-Privilege Access

The EC2 instance role needs:

- Main queue: `sqs:SendMessage`, `sqs:ReceiveMessage`,
  `sqs:DeleteMessage`, `sqs:ChangeMessageVisibility`,
  `sqs:GetQueueAttributes`.
- Quarantine S3 prefix: `s3:PutObject`, `s3:GetObject`,
  `s3:DeleteObject`.
- Approved source prefix: the existing upload permissions.
- Textract, only when OCR is enabled:
  `textract:StartDocumentTextDetection` and
  `textract:GetDocumentTextDetection`.
- KMS permissions required by the selected S3 key, if a customer-managed key is
  used.

Scope queue actions to the created queue ARN and S3 actions to the exact bucket
prefixes. Do not grant wildcard account administration.

### 6. Install the Worker

Install `deployment/systemd/askvera-ingestion-worker.service` and reload
systemd, but do not start or enable it while queueing is disabled. Review its
environment file and service sandbox first.

Rollback: stop and disable the worker.

### 7. Enable Durable Queueing

Set `ADMIN_INGESTION_QUEUE_ENABLED=true`, restart the API, then start and enable
the worker. Upload one non-production test document and verify:

1. The API returns a queued job.
2. The file exists under the quarantine prefix with encryption.
3. The queue message contains only metadata and an S3 URI.
4. The worker completes the job.
5. A failure is retried and eventually reaches the dead-letter queue.
6. A long-running test receives visibility extensions and is not processed by
   two workers.
7. `scripts/reconcile_ingestion_dlq.py --load-ssm` lists the dead-lettered job
   without changing it; apply reconciliation only after review.

Rollback: set the flag to `false` and restart the API. Existing queued messages
remain available for controlled processing.

### 8. Enable Staged Publication

Set `ADMIN_INGESTION_STAGED_PUBLISH_ENABLED=true` while leaving generation
filtering off. Before enabling generation filtering, run
`scripts/backfill_active_generation_pointers.py --load-ssm` in dry-run mode,
review every source identity, and resolve any source with multiple active
ingestion IDs. Apply the backfill, then require
`scripts/validate_ingestion_rollout.py --load-ssm` to pass. This proves every
currently active OpenSearch generation has exactly one matching RDS pointer;
otherwise enabling the filter could hide untouched documents.

Upload a test replacement and confirm the expected staging count is complete.
Then enable `ADMIN_INGESTION_GENERATION_POINTER_ENABLED` and verify each RDS
pointer exposes one complete generation. Run country/language isolation tests
and the retrieval regression suite.

Rollback: restore the prior RDS generation pointer, clear the pointer cache, and
then disable the flag if needed. Retired generations remain indexed during the
rollback window.

### 9. Enable OCR

Set `ADMIN_TEXTRACT_OCR_ENABLED=true` only after Textract permissions and cost
monitoring are in place. Test a scanned PDF and confirm page ordering, section
counts, locale metadata, and retrieval quality before publication.

Rollback: set the flag to `false`; scanned documents return to the existing
preflight rejection path.

### 10. Start Retention Cleanup

Review legal and operational retention periods, install
`askvera-retention.service` and `askvera-retention.timer`, then run the service
once manually and inspect deletion counts. The timer runs daily with a
randomized delay.

Review `deployment/knowledge-ingestion-lifecycle.json`, then create an S3
lifecycle rule that expires quarantine objects after the approved period.
`scripts/cleanup_knowledge_artifacts.py --load-ssm` is dry-run-only unless
`--apply` is supplied. Keep approved source documents under their separate
document-retention policy.

Rollback: disable the timer. Database deletions cannot be undone without a
backup, so confirm backups and retention approvals before the first run.

### 11. Enforce the Hardened Profile

After all required controls are verified, set `SECURITY_PROFILE=hardened`.
Startup validation then refuses to run if a required security feature or
destination is missing.

Rollback: set `SECURITY_PROFILE=standard` only through the approved emergency
change process.

### 12. Portal MFA and WAF

Review the `deployment/admin-portal.yaml` change set. MFA enrollment affects
every administrator, so notify users before applying it. Enable the Web ACL
with `EnableWebAcl=true` only after reviewing rate limits and managed-rule
metrics in count/testing conditions where appropriate.

Rollback: set `EnableWebAcl=false` if legitimate portal traffic is blocked.
Cognito MFA rollback requires a deliberate identity-policy decision.

### 13. Deployment Authentication and Diagnostics

GitHub widget deployment uses OpenID Connect to assume an approved, narrowly
scoped AWS deployment role. Configure `AWS_DEPLOY_ROLE_ARN` in repository
secrets and do not restore long-lived AWS access-key secrets.

Use unauthenticated `GET /health` for load balancers and availability checks.
The diagnostic `GET /health/deep` endpoint requires an authenticated operations
administrator because it reveals dependency state. The operations portal
production build does not publish JavaScript source maps.

## Required Verification

- Python unit tests and lint pass.
- Widget type-check, build, and artifact validation pass.
- CloudFormation templates pass `validate-template` and change-set review.
- Existing retrieval evaluation remains at or above the current approved
  baseline.
- Cross-market and cross-language isolation tests pass.
- One queue retry and one dead-letter scenario are observed.
- One scanned PDF is verified page by page before OCR publication.
- Database backup restore procedure is confirmed before retention starts.

## Operational Monitoring

Monitor queue depth, oldest-message age, dead-letter count, ingestion job
failure rate, Textract errors, OpenSearch activation failures, API health,
administrator sign-in failures, WAF blocked requests, and daily retention
deletion counts.
