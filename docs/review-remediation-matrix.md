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
| 1 | Stored XSS in legal HTML | Implemented locally; full CI verification required | Server and widget sanitizers use strict allowlists; unsafe print-time `document.write` was removed. |
| 2 | Durable ingestion | Implemented locally; full CI verification and deployment required | Quarantine S3 storage, content validation, optional malware-scan enforcement, atomic worker leases, explicit retry/terminal states, SQS/DLQ reconciliation, alarms, and systemd are implemented behind disabled flags. |
| 3 | Atomic document replacement | Implemented locally; full CI verification and deployment required | New generations are staged and counted, then a transactional RDS generation pointer changes the visible generation. Retired generations remain available for a bounded rollback period. Retrieval filtering remains disabled by default. |
| 4 | Infrastructure identifiers in source | Implemented and smoke-verified; CI pending | Identifiers now come from environment or SSM. A permanent CI and pre-commit scan blocks account-bearing ARNs, SQS account URLs, presigned credentials, and widget storage bypasses. |
| 5 | Edge WAF protection | Partial | Optional WAF exists for the operations portal. API edge enforcement requires an approved CloudFront or ALB design before implementation. |
| 6 | Security controls disabled by default | Controlled | `SECURITY_PROFILE=hardened` requires durable ingestion, OCR, audit delivery, evidence contracts, and alarms. Flags remain off until infrastructure is approved. |
| 7 | Admin MFA | Complete in template, deployment required | Cognito MFA is enabled in the operations portal infrastructure template. |
| 8 | Retention | Implemented, CI verification pending, scheduling required | Bounded dry-run-first retention covers transcripts, analytics, feedback, support, shadow comparisons, ingestion jobs, sessions, and consent; a systemd timer is provided. |
| 9 | Multilingual PII | Improved | Comprehend is used only for supported languages. Language-neutral fallback covers email, phone, card, government-ID pattern, and checksum-valid IBAN values. |
| 10 | Browser transcript and resumption boundary | Implemented and frontend-verified; CI pending | Session-only storage is the default and all browser persistence uses the storage adapter. Resume capabilities are signed and bound server-side to widget ID, origin, and session. |
| 11 | Evidence contracts | Implemented behind flag; full CI and regression verification required | Structured evidence declarations and validation are implemented but remain disabled pending regression evaluation. |
| 12 | Query planner trust boundary | Implemented locally; full CI verification required | Planner output is schema-validated, enum-limited, and bounded before use. |
| 13 | Freshness and effective dates | Improved locally | Effective-date, owner, approval-reference, and stable logical-document metadata are ingested. Ranking changes based on dates remain deferred pending shadow evaluation. |
| 14 | Retrieval debug mode | Partial | Shadow comparisons and answer-review diagnostics exist. A full administrator evidence-trace UI remains future work. |
| 15 | Knowledge-gap workflow | Partial | Failed and low-confidence responses are visible for review. Automated assignment and ticket lifecycle are not yet implemented. |
| 16 | Market scorecard | Partial | Shadow report and analytics data exist; a dedicated market-by-market retrieval scorecard remains future work. |
| 17 | OCR and tables | Implemented locally; full CI verification and deployment required | Preflight detects scanned/table-like PDFs, table-like pages preserve layout, and Textract OCR is available behind flags. |
| 18 | Integrity and provenance | Improved locally | SHA-256 is verified from accepted upload through worker processing. The accepting administrator, document owner, approval reference, stable logical ID, and effective date are recorded. Signed manifests remain optional future hardening. |

## Deployment Gates

Before enabling any new production feature:

1. Populate and validate all required SSM settings.
2. Run `scripts/validate_config.py --load-ssm` without changing the service.
3. Dry-run and then apply the ordered database migrations with `scripts/run_db_migrations.py`.
4. Run `scripts/backfill_active_generation_pointers.py --load-ssm` as a
   read-only dry run and review every reported source identity.
5. Apply the pointer backfill only after the dry run is approved, then rerun it
   and require exact pointer coverage with no mismatches or orphaned pointers.
6. Run `scripts/validate_ingestion_rollout.py --load-ssm` before restarting any
   service. This check is read-only and must report no pending migrations,
   mapping defects, or generation-coverage failures.
7. Deploy the ingestion queue and IAM permissions.
8. Install but do not start the ingestion worker until a UAT upload succeeds.
9. Require a green GitHub CI run; local Python tests are not a substitute.
10. Run the existing retrieval evaluation against the unchanged active index.
11. Run shadow evaluation against the isolated vNext index.
12. Enable one feature flag at a time with rollback instructions recorded.

## Verification Evidence

- Python source compilation: passed locally.
- Security regression scan: passed locally.
- Widget type-check, production build, and artifact validation: passed locally.
- Operations portal TypeScript and production build: passed locally.
- Full Python unit suite: pending GitHub CI because the existing local dependency bundle is incomplete and cannot execute pytest/flake8. Every locally implemented status remains provisional until CI is green.

## Explicitly Deferred

- Switching active retrieval to vNext chunking or reranking
- Replacing the active OpenSearch index
- Date-based ranking changes
- API edge/WAF redesign
- Signed ingestion manifests
- Automated gap-to-ticket workflow

These items need architecture approval or measured UAT evidence and are intentionally not part of the current local change set.
