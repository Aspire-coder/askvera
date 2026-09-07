# Active-source metadata export and review

Captured 2026-09-06 from the existing AWS test database. Raw artifact: `active-source-metadata.json`.

## Verified

- Export ran using an explicit read-only, repeatable-read PostgreSQL transaction with a 15-second statement timeout.
- Connection used PostgreSQL TLS (`sslmode=require`) through a loopback-only Systems Manager tunnel. This run did not use explicit `verify-full` certificate/hostname validation.
- Credentials resolved only through the approved asm-exec wrapper and temporary signed local AWS helper; no credential values were displayed or written to the artifact.
- 29 active-generation entries, 29 document records, 43 generation-history records.
- Every active ingestion ID exists in generation history. All 29 document records have content hashes; hashes have not yet been checked against S3 file bytes or indexed chunks.
- Temporary helper stopped; SSM session `pavan410-lzo98iqzsi6xtdotioyvetadn4` terminated successfully. No remaining listeners were returned for ports 15432 and 2773.

## Metadata inconsistencies to trace before evaluation

1. UK policy uses `UK` in active-generation metadata but `GB` in the document registry. Their logical-document IDs therefore differ.
2. Both global directories have blank logical-document IDs in the document registry, while their active-generation entries have populated IDs.
3. Thirteen document records have blank human-readable version labels. Content hashes are populated, so version-label absence alone does not prove absent content.
4. The April 2026 global office-directory registry record reports zero sections while an active-generation entry exists. This is not proof that its index is empty; verify the actual indexed generation.

These are observed registry inconsistencies, not established causes of the chatbot's answer failures. Do not rewrite country codes, manufacture versions, or backfill identifiers without tracing publication and indexed evidence.

## Next verification

Read the indexed metadata for the exact active ingestion IDs, prioritizing US policy, UK policy, and both global directories. Match source identifiers, source links, hashes, locale, and section counts. Preserve aliases as observed when building the snapshot rather than silently normalizing Current into Candidate. Then freeze the same source snapshot and settings for both code versions and capture full answers, citations, and timings.

No database data changed, no model calls were made, and no chatbot code was deployed. Full Current/Candidate comparison remains pending; this export does not establish a retrieval improvement percentage.
