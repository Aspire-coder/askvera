# Terra handoff - R02 correction 2

Date: 2026-09-18  
Scope: local-only correction to Astra's R02 findings.  
Next owners: Sol, then Astra. Do not start R03.

## Review record

Sol approved the preceding R02 snapshot:

`10751e6e5e3ba4ee8ab8d135445019af9f871fd5d66436371b414e52102d9720`

Astra then returned **NEEDS CORRECTION**. This correction addresses only its
three stated findings: OpenSearch response completeness, degraded retrieval
without approved evidence, and durable review recording. The separately known
`capture_provenance` isolation allowlist mismatch remains queued and untouched.

## Reproduced defects

Before this correction, the new controls demonstrated that:

1. A response with `timed_out: true` and valid hits was marked `available`.
2. A response with `_shards.failed: 1` and a 503 shard failure was marked
   `available`.
3. A 400 `query_shard_exception` response was treated as a completed search,
   leading to a later unrelated search and hiding the cause.
4. An empty text result plus vector timeout became `degraded`, then reached
   the evidence gate and claimed that documents were insufficient.
5. Retrieval health recorded an empty degraded result as successful.

The pre-fix controls failed with these exact six symptoms before the code was
changed.

## Correction

### Response completeness

`OpenSearchSectionProvider._search_channel` now inspects a completed response
before declaring the channel successful:

- `timed_out: true` preserves any returned hits, records a `timed_out` channel
  failure, and makes the overall result degraded.
- `_shards.failed > 0` preserves returned hits only for explicitly transient
  shard types or 5xx shard statuses. It records a `shard_failure` with the
  failed shard count.
- Shard responses with index, request, mapping, validation, authentication,
  authorization, or other 4xx failure signals raise `RequestError` for
  diagnosis.
- An unclassified failed-shard response also raises rather than being silently
  treated as a transient outage.

This behavior applies to exact, local text/vector, outline, and global
directory channels. Metadata now includes `search_channel_failures` alongside
`failed_search_channels`.

### Degraded retrieval with no approved evidence

The retrieval service records a degraded result as healthy only when it has
usable documents. An empty degraded result records failure health.

The orchestrator still permits degraded retrieval with approved evidence to
answer normally. If a degraded result has no approved evidence, it now returns
the localized `dependency_unavailable` response before document-insufficiency
fallback logic. This prevents a partial provider outage from being described
as a policy-document gap.

## Changed paths

- `app/retrieval/opensearch_sections.py`
- `app/retrieval/service.py`
- `app/orchestrator/chat_orchestrator.py`
- `tests/unit/test_opensearch_sections.py`
- `tests/unit/test_retrieval_service.py`
- `tests/unit/test_chat_orchestrator.py`
- `docs/evidence_first_v2/CURRENT_STATUS.md`
- this handoff

All pre-existing V2 changes in shared files remain preserved. No Claude
worktree, isolation allowlist, frozen pack, deployment artifact, or external
service was modified.

## Verification

| Check | Result |
| --- | --- |
| Focused provider, approval, contract, orchestrator, service, and rank-capture suite | 362 passed, exit 0 |
| V2 compatibility plus rank-capture and retrieval-service suite | 218 passed, 1 known isolation failure, exit 1 |
| Targeted flake8 | exit 0 |
| `git diff --check` | exit 0 |

Focused controls include:

- complete local responses with `timed_out: false` and zero failed shards;
- partial local timeout and 503 shard responses with valid hits;
- local request-shard configuration failure propagation;
- partial global timeout with valid directory evidence;
- global index-shard configuration failure propagation;
- degraded local and global evidence that remains answerable; and
- degraded retrieval with no documents, which now receives dependency copy and
  failure health accounting.

The only compatibility failure remains the unrelated
`scope_aware_fusion.py` relative `capture_provenance` allowlist mismatch. This
correction does not change that file, its import allowlist, or the V2-10
boundary.

## Stable correction identity

Base HEAD: `5b1d33fe37167e2a1384e47ac0fa1fe08ea3aee7`

R02 correction 2 file-set SHA-256:

`1249debed89a0e517d3d5a0fe20db658d00ff2a1e922b3cfccf7a81c5f997650`

The identity uses the same exact R02 application-and-test file set as
Correction 1: `app/evidence.py`, `app/orchestrator/chat_orchestrator.py`, the
six retrieval/replay files, and the five R02 test files listed in
`TERRA-R02-CORRECTION-1.md`.

It is the SHA-256 of raw `git diff --binary HEAD -- <that file set>` after
removing exactly one terminal LF byte when present. The raw stream was 99,447
bytes and the canonical stream was 99,446 bytes. This gives a stable snapshot
identity across review/export paths that differ only in the final diff newline;
it is not a release or clean-worktree identity.

## Limits

- No AWS, OpenSearch cluster, network, Bedrock/model call, deployment, merge,
  push, reindex, installation, or frozen-pack change occurred.
- This validates local response semantics and fallback routing. It does not
  establish live outage behavior, alarm routing, answer quality, or release
  readiness.
- R03 remains paused until Sol independently reviews this correction and Astra
  performs the final milestone review.
