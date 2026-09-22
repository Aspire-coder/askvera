# Terra handoff - R02 correction 4

Date: 2026-09-18  
Scope: local-only correction to Astra's final R02 routing finding.  
Next owners: Sol, then Astra. Do not start R03.

## Review history and boundary

Sol approved R02 correction 3 snapshot
`ce514f371bfcfccd8dc2d8bd782a06d54ab1cf25a762d18c1fe36ce62379f815`.
Astra then returned **NEEDS CORRECTION** for one remaining routing defect:
the degraded/no-approved-evidence decision occurred before country-scope
reapproval. This correction changes only that ordering and its direct controls.

The known `capture_provenance` isolation allowlist mismatch remains queued,
separate, and unchanged. All earlier R02 availability, shard validation,
degraded-empty routing, and health behavior remains in place.

## Reproduction before the correction

Two local controls failed before the code change:

1. A US session asked for Mexico's office phone. The retrieval result was
   `degraded` because global directory channels failed, while a local US
   document initially approved. Country-scope reapproval then removed the US
   document, but the earlier dependency check had already been skipped. The
   result reached `evidence_gate` rather than returning the dependency
   disclosure.
2. A degraded US-session request for Mexico company-policy qualifications was
   converted to a dependency response before its legitimate
   `cross_market_policy_request` scope refusal could be returned.

The pre-fix controls produced two failures, exit 1.

## Correction

`AIOrchestrator._route_or_approve_evidence` now performs country-scope
reapproval first, creates the final approved-evidence result, and only then
uses the degraded dependency fallback when the final decision has no approved
evidence.

The one explicit exception is `cross_market_policy_request`: a request for
another country's company policy remains an evidence-gate scope refusal, even
when retrieval is degraded. A degraded request with final usable local or
global evidence still continues normally.

The dependency response retains `failure_layer: dependency_unavailable` and
`retrieval_availability: degraded`. The returned retrieval result retains its
provider availability and failed-channel metadata for health and diagnostics.

## Changed paths

- `app/orchestrator/chat_orchestrator.py`
- `tests/unit/test_chat_orchestrator.py`
- `docs/evidence_first_v2/CURRENT_STATUS.md`
- this handoff

No unrelated Evidence-First V2 or Claude worktree file was edited.

## Verification

| Check | Result |
| --- | --- |
| Pre-fix exact routing and policy controls | 2 failed, exit 1 |
| Post-fix routing controls | 6 passed, exit 0 |
| Focused provider, approval, contract, orchestrator, service, and rank-capture suite | 367 passed, exit 0 |
| V2 compatibility plus rank-capture and retrieval-service suite | 218 passed, 1 known isolation failure, exit 1 |
| Targeted flake8 | exit 0 |
| `git diff --check` | exit 0 |

The controls include the exact Mexico/global-directory loss regression and
assert its dependency failure layer and degraded availability; degraded local
and global evidence that still answers; the existing empty-degraded health
failure and usable-degraded health-success controls; and the Mexico
company-policy scope-refusal control, which asserts `evidence_gate` rather
than a dependency response.

The only compatibility failure remains the pre-existing, separately recorded
`scope_aware_fusion.py` relative `capture_provenance` allowlist mismatch. This
correction does not edit that import, its allowlist, or the V2-10 boundary.

## Stable correction identity

Base HEAD: `5b1d33fe37167e2a1384e47ac0fa1fe08ea3aee7`

R02 correction 4 file-set SHA-256:

`fcecd93e790046d4c2bb8687c4f191691545df4c19bde74ac36b3d32b13e59c3`

The identity is the SHA-256 of `git diff --binary HEAD --` for the same 13
R02 application/test paths as corrections 2 and 3: `app/evidence.py`,
`app/orchestrator/chat_orchestrator.py`, `app/retrieval/__init__.py`,
`app/retrieval/models.py`, `app/retrieval/opensearch_sections.py`,
`app/retrieval/providers.py`, `app/retrieval/service.py`,
`scripts/offline_retrieval_replay.py`, and the five R02 unit test files.

The raw diff stream was 106,802 bytes. The canonical stream was 106,801 bytes
after removing one final LF when present before hashing. The digest identifies
this selected dirty snapshot only. It is not a clean-worktree, release, or
production identity.

## Limits and next review

- No AWS, network, OpenSearch cluster, model, deployment, merge, push,
  installation, or frozen-pack change occurred.
- Local tests establish ordering, scope, availability, failure-layer and health
  semantics only. They do not establish live outage behavior, answer quality,
  alarm routing, or release readiness.
- R03 remains paused. Send this exact snapshot to fresh Sol review, then Astra
  final review.
