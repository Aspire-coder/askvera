# Terra handoff - R02 correction 1

Date: 2026-09-18  
Scope: local-only correction to Sol's R02 review findings.  
Next owner: Sol for a fresh independent review. Do not start R03.

## Corrected findings

### Availability survives evidence transformations

Both result reconstruction paths now copy the provider's typed availability:

- `app/evidence.py::with_approved_evidence`
- `app/orchestrator/chat_orchestrator.py::AIOrchestrator._apply_evidence_contract`

Before this correction, a provider result with `availability=degraded` became
the dataclass default `available` after either reconstruction. The failure
metadata remained, but the typed signal consumed by downstream code was lost.
After this correction, `available`, `degraded`, and `unavailable` each survive
approval and evidence-contract acceptance unchanged.

The end-to-end evidence-routing control proves that a degraded provider result
with usable US policy evidence is approved and returned as `degraded`; it does
not become `available` while passing through the evidence gate.

### OpenSearch exception boundary

`OpenSearchSectionProvider._search_channel` now converts only these failures
into a failed search channel:

- connection, timeout, and SSL failures through `ConnectionError`;
- authentication and authorization failures; and
- generic OpenSearch transport failures whose HTTP status is 500 through 599.

The following now remain visible to the caller for diagnosis:

- `RequestError`;
- `NotFoundError`, including `index_not_found_exception`;
- `ConflictError`;
- other non-5xx `TransportError` values;
- unexpected `OpenSearchException` values; and
- programming or local configuration errors.

This corrects Sol's reproduction where a missing index was silently presented
as transient retrieval unavailability. A real 503 service response remains a
typed provider outage, while a completed empty search remains available.

The rank-list capture test fixture now raises `ConnectionTimeout` rather than
a generic `OpenSearchException` when it models a transport outage. Generic
exceptions are intentionally no longer transport outages under the narrowed
contract.

## Changed paths

Correction-specific changes:

- `app/evidence.py`
- `app/orchestrator/chat_orchestrator.py`
- `app/retrieval/opensearch_sections.py`
- `tests/unit/test_evidence_routing.py`
- `tests/unit/test_chat_orchestrator.py`
- `tests/unit/test_opensearch_sections.py`
- `tests/unit/test_retrieval_rank_list_capture.py`
- `docs/evidence_first_v2/CURRENT_STATUS.md`
- this handoff

The surrounding R02 snapshot also contains the earlier typed availability,
retrieval-service, provider, rank-capture, and replay changes recorded in
`TERRA-R01-R02-OPENSEARCH-AVAILABILITY-HANDOFF.md`. Existing dirty V2 work was
preserved and is not attributed to this correction merely because it shares a
file.

## Verification

All commands used the repository's existing Python runtime, `-p
no:cacheprovider`, and task-owned temporary directories.

| Check | Result |
| --- | --- |
| R02 provider, approval, evidence-contract, orchestrator, health, and rank-capture suite | 352 passed, exit 0 |
| V2 compatibility plus rank-capture and retrieval-service suite | 216 passed, 1 known isolation failure, exit 1 |
| Targeted flake8 | exit 0 |
| `git diff --check` | exit 0 |

The compatibility failure is unchanged and outside R02: the pre-existing V2
isolation allowlist lacks `capture_provenance` for
`scope_aware_fusion.py`. This correction does not edit the allowlist,
`scope_aware_fusion.py`, or the V2-10 boundary.

## Stable correction identity

Base HEAD: `5b1d33fe37167e2a1384e47ac0fa1fe08ea3aee7`

R02 correction file-set SHA-256:

`10751e6e5e3ba4ee8ab8d135445019af9f871fd5d66436371b414e52102d9720`

The identity is the SHA-256 of the raw `git diff --binary HEAD --` output for
this exact file set:

- `app/evidence.py`
- `app/orchestrator/chat_orchestrator.py`
- `app/retrieval/__init__.py`
- `app/retrieval/models.py`
- `app/retrieval/opensearch_sections.py`
- `app/retrieval/providers.py`
- `app/retrieval/service.py`
- `scripts/offline_retrieval_replay.py`
- `tests/unit/test_chat_orchestrator.py`
- `tests/unit/test_evidence_routing.py`
- `tests/unit/test_opensearch_sections.py`
- `tests/unit/test_retrieval_rank_list_capture.py`
- `tests/unit/test_retrieval_service.py`

Before hashing, remove exactly one final LF byte if the binary diff ends with
one. Git emits that final separator, while some review/export paths omit it;
normalizing only that terminal byte gives a stable content identity without
changing any interior newline or diff byte. For this snapshot the raw diff was
82,157 bytes, the canonical stream was 82,156 bytes, and a terminal LF was
removed. The digest identifies the selected dirty snapshot, not a clean
release artifact or an assertion that every hunk in shared files belongs to
R02.

## Limits and non-claims

- No AWS, OpenSearch cluster, Bedrock call, network request, deployment,
  merge, push, reindex, installation, or frozen-pack modification occurred.
- This proves local exception classification and state propagation. It does
  not prove live outage behavior, alarm routing, user-facing answer quality,
  or release readiness.
- A partial provider failure remains `degraded` with usable evidence. Whether
  that state should page is an observability policy decision outside R02.
- R03 remains blocked until Sol independently reviews this correction.
