# Terra handoff - R02 correction 3

Date: 2026-09-18  
Scope: local-only correction to Sol's aggregate shard-validation finding.  
Next owners: Sol, then Astra. Do not start R03.

## Review record and boundary

Sol reviewed R02 correction 2 and returned **NEEDS CORRECTION**. This update
fixes only its shard-failure aggregate-validation finding in
`app/retrieval/opensearch_sections.py` and its focused tests. It does not
change the previously corrected availability propagation, response-level
timeout behavior, degraded-empty fallback, health accounting, or any unrelated
Evidence-First V2 or Claude work.

The known `capture_provenance` isolation allowlist mismatch remains queued
separately and unchanged.

## Reproduction before the correction

Two controls failed before the code change:

1. One response reported two failed shards: one known transient
   `unavailable_shards_exception`, one `unknown_shard_failure`. The old
   aggregate `any(...)` rule accepted the channel because one failure was
   transient.
2. A response reported `_shards.failed: 2` but supplied only one 503 failure
   diagnostic. The old rule accepted the incomplete list.

The new positive control, with two independently acceptable failures, already
passed before and after the change. It proves this is not a blanket rejection
of partial results.

## Correction

`OpenSearchSectionProvider._response_failures` now:

- requires the diagnostics list length to equal `_shards.failed` exactly;
- validates every diagnostic independently;
- raises for any configuration, query, index, mapping, validation, unknown or
  unsupported failure, and for any 4xx status; and
- preserves partial hits only when every failure has either a recognized
  transient type or an explicit 5xx status.

This applies identically to local and global channels because both use the
same `_search_channel` response contract. Mixed valid and invalid diagnostics
therefore fail closed rather than becoming a misleading degraded result.

## Changed paths

- `app/retrieval/opensearch_sections.py`
- `tests/unit/test_opensearch_sections.py`
- `docs/evidence_first_v2/CURRENT_STATUS.md`
- this handoff

All other R02 paths remain in the selected review identity because this is a
dirty experimental worktree and the stable review snapshot must include the
full application-and-test R02 boundary. No unrelated V2 or Claude changes
were edited.

## Verification

| Check | Result |
| --- | --- |
| Pre-fix aggregate controls | 2 failed, 1 passed, exit 1 |
| Post-fix shard controls | 6 passed, exit 0 |
| Focused provider, approval, contract, orchestrator, service, and rank-capture suite | 365 passed, exit 0 |
| V2 compatibility plus rank-capture and retrieval-service suite | 218 passed, 1 known isolation failure, exit 1 |
| Targeted flake8 | exit 0 |
| `git diff --check` | exit 0 |

The compatibility failure is unchanged and outside R02:
`scope_aware_fusion.py` imports `capture_provenance`, which the existing V2
isolation allowlist excludes. This correction does not change the import, its
allowlist, or the V2-10 boundary.

The new focused controls cover:

- a local mixed transient-plus-unknown list, rejected;
- a local incomplete list, rejected;
- multiple independently valid transient and explicit-5xx failures, retained
  as degraded partial evidence; and
- the prior local/global configuration and partial-service response controls.

## Stable correction identity

Base HEAD: `5b1d33fe37167e2a1384e47ac0fa1fe08ea3aee7`

R02 correction 3 file-set SHA-256:

`ce514f371bfcfccd8dc2d8bd782a06d54ab1cf25a762d18c1fe36ce62379f815`

The identity is the SHA-256 of `git diff --binary HEAD --` for the same exact
13 application/test paths used by correction 2: `app/evidence.py`,
`app/orchestrator/chat_orchestrator.py`, `app/retrieval/__init__.py`,
`app/retrieval/models.py`, `app/retrieval/opensearch_sections.py`,
`app/retrieval/providers.py`, `app/retrieval/service.py`,
`scripts/offline_retrieval_replay.py`, and the five R02 unit test files.

The raw diff stream was 103,470 bytes. The canonical stream was 103,469 bytes
after removing one final LF when present before hashing. The digest identifies
this selected dirty snapshot only; it is not a clean-worktree, release, or
production identity.

## Limits and next review

- No AWS, network, OpenSearch cluster, model, deployment, merge, push,
  installation, or frozen-pack change occurred.
- Local controls establish only response-classification behavior. They do not
  prove live outage behavior, alarm routing, answer quality, or release
  readiness.
- R03 remains paused. Send this exact snapshot to fresh Sol review, then Astra
  final review.
