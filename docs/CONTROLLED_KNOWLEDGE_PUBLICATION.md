# Controlled Knowledge Publication

## Purpose

This change makes policy and global-office-directory uploads reviewable,
retry-safe, and atomically replaceable. It does not change the active UAT
retrieval query, ranking, prompt, cache, model, widget assets, markets, or
languages while the new flags remain disabled.

## Supported Content

- Country-scoped company policies
- The globally accessible office directory

Product information, ordering content, training material, and general FAQs are
outside the current AskVera knowledge scope.

## Publication Flow

1. An administrator uploads an approved document with its stable logical
   document ID, owner, approval reference, version, and effective date.
2. The API validates the file type, content signature, declared market,
   language, scope, and approval metadata.
3. The original file is stored under the private quarantine prefix.
4. A compact SQS command carries metadata and the S3 URI, not document content.
5. The worker claims the job with a lease and verifies the SHA-256 hash.
6. When malware enforcement is enabled, the worker waits for a `CLEAN` scan tag.
7. Native policy PDFs use the policy-aware structural extractor. Scanned PDFs
   use Textract when OCR is enabled. Directory and other approved non-policy
   files use the bounded generic extractor.
8. Every OpenSearch record receives country, language, access scope, document
   type, ingestion ID, and logical document ID metadata.
9. The complete new generation is staged and counted.
10. A database transaction retires the prior generation and selects the new
    active generation for that logical document.
11. Retrieval uses the active-generation pointer only after the feature flag is
    enabled. With the flag disabled, the existing UAT query shape is unchanged.
12. Retired generations remain available for rollback until the approved
    retention window expires.

## Failure Handling

- Invalid commands, unsafe files, unsupported locale/scope combinations, and
  hash mismatches become terminal failures.
- Temporary AWS, database, malware-scan, or file-system failures return to SQS
  until the bounded attempt count is reached.
- Exhausted commands move to the retained DLQ.
- `scripts/reconcile_ingestion_dlq.py` previews DLQ jobs by default and requires
  `--apply` to mark them `dead_lettered` and remove the matched command.
- No failed or partial generation can become the active retrieval generation.

## Retention

- Quarantine cleanup is based on
  `ADMIN_INGESTION_QUARANTINE_RETENTION_DAYS`.
- Retired generation cleanup is based on
  `ADMIN_INGESTION_RETIRED_GENERATION_RETENTION_DAYS`.
- `scripts/cleanup_knowledge_artifacts.py` is a dry run unless `--apply` is
  explicitly supplied.
- OpenSearch cleanup scans all matching records rather than relying on a
  10,000-result cap.

## Safe Rollout

1. Keep all new flags disabled.
2. Require green CI.
3. Populate SSM values.
4. Dry-run and apply database migrations.
5. Run `scripts/backfill_active_generation_pointers.py --load-ssm` as a dry
   run. Review every active logical document and resolve any ambiguous active
   generations.
6. Run the same command with `--apply`, then run
   `scripts/validate_ingestion_rollout.py --load-ssm`. The validator refuses
   readiness when an active OpenSearch generation is missing a matching RDS
   pointer, points to a different generation, or has an orphaned pointer.
7. Deploy queue, DLQ, S3 lifecycle, IAM permissions, and worker service.
8. Start with one non-production policy replacement.
9. Verify extraction, counts, locale isolation, citations, and rollback.
10. Enable staged publication.
11. Enable the generation pointer only after every currently active document
    has pointer coverage and the UAT retrieval evaluation
    remains at or above its approved baseline.
12. Enable approval metadata and malware enforcement.
13. Set the hardened security profile last.

## Rollback

The fastest content rollback is to restore the previous
`active_ingestion_id` for the affected logical document in
`knowledge_active_generations`, clear the application pointer cache, and rerun
the locale-specific retrieval checks. Do not delete the retired generation
until its rollback window has elapsed.

## Verification Status

Local source compilation and patch-integrity checks pass. Full Python unit and
lint verification remains a release gate in GitHub CI because the existing
local dependency bundle is incomplete. Local implementation labels are
provisional until CI is green.
