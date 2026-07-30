# AskVera Review Remediation Matrix

This document records the implementation status of the architecture and security review without changing the active UAT retrieval behavior.

## Release Boundary

The following production behavior remains unchanged in this batch:

- Active retrieval provider and OpenSearch index
- Hybrid query construction and ranking weights
- Evidence selection and answer prompt
- Cache keys and cache duration
- Widget release assets
- Country and language availability

All retrieval experiments remain isolated behind disabled feature flags and a separate vNext index.

## Findings

| # | Review area | Status | Implementation or next control |
|---|---|---|---|
| 1 | Stored XSS in legal HTML | Complete locally | Server and widget sanitizers use strict allowlists; unsafe print-time `document.write` was removed. |
| 2 | Durable ingestion | Implemented, CI verification pending, deployment required | Quarantine S3 storage, content validation, optional malware-scan enforcement, atomic worker leases, bounded retries, SQS/DLQ, alarms, and systemd are implemented behind disabled flags. |
| 3 | Atomic document replacement | Partial | New generations are staged, counted, activated, and rolled back on activation error. A future alias or generation-pointer design is still required to eliminate the brief old/new overlap during cleanup. |
| 4 | Infrastructure identifiers in source | Implemented and smoke-verified; CI pending | Identifiers now come from environment or SSM. A permanent CI and pre-commit scan blocks account-bearing ARNs, SQS account URLs, presigned credentials, and widget storage bypasses. |
| 5 | Edge WAF protection | Partial | Optional WAF exists for the operations portal. API edge enforcement requires an approved CloudFront or ALB design before implementation. |
| 6 | Security controls disabled by default | Controlled | `SECURITY_PROFILE=hardened` requires durable ingestion, OCR, audit delivery, evidence contracts, and alarms. Flags remain off until infrastructure is approved. |
| 7 | Admin MFA | Complete in template, deployment required | Cognito MFA is enabled in the operations portal infrastructure template. |
| 8 | Retention | Implemented, CI verification pending, scheduling required | Bounded dry-run-first retention covers transcripts, analytics, feedback, support, shadow comparisons, ingestion jobs, sessions, and consent; a systemd timer is provided. |
| 9 | Multilingual PII | Improved | Comprehend is used only for supported languages. Language-neutral fallback covers email, phone, card, government-ID pattern, and checksum-valid IBAN values. |
| 10 | Browser transcript and resumption boundary | Implemented and frontend-verified; CI pending | Session-only storage is the default and all browser persistence uses the storage adapter. Resume capabilities are signed and bound server-side to widget ID, origin, and session. |
| 11 | Evidence contracts | Complete behind flag | Structured evidence declarations and validation are implemented but remain disabled pending regression evaluation. |
| 12 | Query planner trust boundary | Complete | Planner output is schema-validated, enum-limited, and bounded before use. |
| 13 | Freshness and effective dates | Partial | Effective-date metadata is ingested. Ranking changes based on dates require a shadow evaluation before rollout. |
| 14 | Retrieval debug mode | Partial | Shadow comparisons and answer-review diagnostics exist. A full administrator evidence-trace UI remains future work. |
| 15 | Knowledge-gap workflow | Partial | Failed and low-confidence responses are visible for review. Automated assignment and ticket lifecycle are not yet implemented. |
| 16 | Market scorecard | Partial | Shadow report and analytics data exist; a dedicated market-by-market retrieval scorecard remains future work. |
| 17 | OCR and tables | Complete locally, deployment required | Preflight detects scanned/table-like PDFs, table-like pages preserve layout, and Textract OCR is available behind flags. |
| 18 | Integrity and provenance | Improved | SHA-256 is verified from accepted upload through worker processing and stored with indexed-document metadata. The accepting administrator is now recorded. Signed manifests remain optional future hardening. |

## Deployment Gates

Before enabling any new production feature:

1. Populate and validate all required SSM settings.
2. Run `scripts/validate_config.py --load-ssm` without changing the service.
3. Dry-run and then apply the ordered database migrations with `scripts/run_db_migrations.py`.
4. Deploy the ingestion queue and IAM permissions.
5. Install but do not start the ingestion worker until a UAT upload succeeds.
6. Require a green GitHub CI run; local Python tests are not a substitute.
7. Run the existing retrieval evaluation against the unchanged active index.
8. Run shadow evaluation against the isolated vNext index.
9. Enable one feature flag at a time with rollback instructions recorded.

## Verification Evidence

- Python source compilation: passed locally.
- Security regression scan: passed locally.
- Widget type-check, production build, and artifact validation: passed locally.
- Operations portal TypeScript and production build: passed locally.
- Full Python unit suite: pending GitHub CI because the existing local dependency bundle is incomplete and cannot execute pytest/flake8.

## Explicitly Deferred

- Switching active retrieval to vNext chunking or reranking
- Replacing the active OpenSearch index
- Date-based ranking changes
- API edge/WAF redesign
- Signed ingestion manifests
- Automated gap-to-ticket workflow

These items need architecture approval or measured UAT evidence and are intentionally not part of the current local change set.
