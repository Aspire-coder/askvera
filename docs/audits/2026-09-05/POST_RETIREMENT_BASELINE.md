# Post-retirement source baseline - 2026-09-06

Status: source identity and selected publication coverage verified. Matched Current/Candidate full-answer comparison NOT RUN. No improvement percentage established.

## Confirmed

- Fresh read-only registry capture: `active-source-metadata-after-retirement.json`, 2026-09-06T04:35:13.486461+00:00.
- 28 active publications. The only removed active ingestion ID relative to the prior capture is `8ac8b5ef5187468cbe167f313a5e165e`; no new active IDs appeared.
- International-Sponsoring-Directory.pdf is the sole active global publication. Its legacy `document_type` remains `office_directory`; this type label does not mean the retired April office directory remains active.
- April office directory retirement is recoverable. No S3 source object was deleted.
- Fresh index audit `active-index-metadata-after-retirement.json` returned complete exact totals: UK English 728, US English 435, sponsoring 113. These are section counts, not passed questions.
- Three approved PDFs were read in full from S3 with ETag/version pinning and byte-count verification. Actual PDF SHA-256, S3 version IDs and locations are recorded in `comparison-source-file-hashes.json`.

## Hash interpretation

The earlier artifact's `registry_hash_matches: false` means only that the registry value differs from the PDF-byte SHA-256. It is NOT a corruption verdict.

- `register_global_directory_documents.py` hashes `source_uri + ':' + ETag`. Recomputing this formula for the sponsoring source exactly matches its registry hash.
- `backfill_document_registry.py` hashes nonblank processed JSONL lines, excluding line separators. It does not hash the original PDF. This explains why historical registry hashes cannot universally be treated as PDF hashes; the US/UK historical JSONL bytes have not been re-hashed in this check.
- The index writer hashes individual chunk content. This is a third identity level and must be tested separately.

## Remaining before comparison

1. Capture actual indexed evidence text and verify per-chunk hashes; source-object checks alone do not prove extraction correctness.
2. Freeze effective settings, actual prompt text hash and both code identities. The deployed revision last inspected was `7d29dad09540527a9302b95436f36e93f7fa5a2a`; local changes are uncommitted. This is not a fresh deployment attestation.
3. Build a bounded local harness that preserves publication, country/global, evidence and output safeguards, while isolating session state and shared writes/cache. Do not start a second full app on the small EC2 instance.
4. Capture the same questions, both complete answers, citations, failure layers and timings across repeated runs. Report in-scope, safety and Legal completeness separately.

The secure credential-wrapper backend is now working; the earlier preflight's credential-access blocker is resolved. This refresh used runtime credential references through asm-exec, a temporary loopback helper, and an SSM tunnel. Both temporary processes/connections were stopped. No application deployment, index mutation or additional database mutation was performed for this refresh. Registry and index reads are not an atomic cross-service snapshot.
