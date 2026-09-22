# Evidence-First V2 - authoritative current status

**As of 2026-09-18.** This is the current working-status record for
Evidence-First V2. It supplements, rather than edits or invalidates, the
historical evidence in `output/evidence-first-v2/STATUS.md` and the V2-09 and
V2-10 handoffs.

## Baseline and boundaries

- Worktree: `askvera-evidence-first-v2`, branch
  `experiment/evidence-first-v2-20260917`, base
  `5b1d33fe37167e2a1384e47ac0fa1fe08ea3aee7`.
- The worktree was already dirty when R01 began. It contains the experimental
  V2 package plus rank-list capture, provenance, provider, OpenSearch and
  orchestrator changes. Those changes are preserved; this record is not a
  claim that they are merged, released or production-ready.
- V2-09 was an accepted, local-only scope-aware-fusion review. Its replay
  measurements are historical and are not evidence for the current dirty
  code. V2-10 was an accepted, local-only provenance-contract review; its
  required new capture has not been authorized or run.
- The old output status log is stale as a current-state source. In particular,
  it must not be read as saying that a current V2 candidate is clean, that old
  replay scores apply to later code, or that a live capture occurred.

## Current milestones

| Milestone | Current state | Evidence and next owner |
| --- | --- | --- |
| R01 - baseline and ownership | Complete locally | This record reconciles the base, dirty state, V2-09/V2-10 limits and ownership. |
| R02 - provider outage honesty | Accepted for the local milestone | Sol approved and Astra approved with limitations at snapshot `fcecd93e790046d4c2bb8687c4f191691545df4c19bde74ac36b3d32b13e59c3`. Degraded dependency disclosure waits for final post-scope evidence approval, while foreign policy-scope refusals remain evidence-gated. See `TERRA-R02-CORRECTION-4.md`. |
| R03 - context-to-capture | Complete locally, awaiting Sol review | Sol found Correction 6 returned on the first configured form and missed competing direct/unknown signals; Astra required one bounded decision-order correction. `TERRA-R03-CORRECTION-7-20260918-1541.md` records it at snapshot `9101284889a4aa074b5dec681075ae3b4539dbe4b977997b92d5db322c078bd6`. |
| R04-R12 | Not started | Remain sequenced in `REMAINING-IMPROVEMENTS-PLAN.md`; several later stages need explicit live-run approval. |

## Ownership reconciliation with Claude

The following Claude ownership record is a prior read-only observation, not a
claim about Claude's current worktree. Before any combined integration, it
needs a new read-only refresh at integration time. No Claude worktree was
inspected or edited in this R03 correction.

For shared C5, Codex owns provider state and health truthfulness; Claude owns
localized copy and any dependency/fallback alarm policy. R02 implements the
typed result form of Claude's C5 request:

- `available`: a completed search, including a legitimate empty result;
- `degraded`: at least one channel failed but another completed, with the
  failed channels recorded; and
- `unavailable`: no channel completed because the provider failed.

The orchestrator maps `unavailable`, plus `degraded` retrieval with no usable
final evidence after country-scope reapproval, to Claude's existing localized
technical-dependency response. A foreign company-policy request remains a
scope refusal rather than being relabelled as a dependency outage. Invalid
request and local configuration errors are also deliberately not relabelled as
a dependency outage. No Claude worktree or ownership boundary was changed.

## R02 review history

- Sol approved snapshot `10751e6e5e3ba4ee8ab8d135445019af9f871fd5d66436371b414e52102d9720` after the first correction.
- Astra then returned **NEEDS CORRECTION**: response-level timeouts and shard
  failures had not been typed, and a degraded result without usable approved
  evidence still used the document-insufficiency path.
- `TERRA-R02-CORRECTION-2.md` records the bounded correction for those
  findings. Sol then returned **NEEDS CORRECTION**: aggregate shard validation
  accepted a mixed transient-and-unknown failure list and incomplete shard
  diagnostics.
- `TERRA-R02-CORRECTION-3.md` records the bounded aggregate-validation
  correction. Sol approved its snapshot
  `ce514f371bfcfccd8dc2d8bd782a06d54ab1cf25a762d18c1fe36ce62379f815`.
- Astra then returned **NEEDS CORRECTION**: a degraded global-directory loss
  could become an `evidence_gate` response because the dependency decision ran
  before country-scope reapproval. It also required the ownership summary to
  describe the degraded post-scope dependency path.
- `TERRA-R02-CORRECTION-4.md` records the bounded routing correction. Sol
  approved it after 379 bounded tests and 218 compatibility tests plus the
  unchanged known isolation failure. Astra then returned **APPROVED WITH
  LIMITATIONS** after independently reproducing the former defect and running
  364 application and health tests. The accepted snapshot is
  `fcecd93e790046d4c2bb8687c4f191691545df4c19bde74ac36b3d32b13e59c3`.
- Astra's recorded limits are: provider health is measured before final
  evidence approval; live behavior and alarm routing remain unverified; the
  separate isolation allowlist mismatch remains open; and combined Claude
  integration has not yet been reviewed.

## Known baseline limitation, kept separate from R02

The V2 isolation allowlist currently rejects the already-present relative
import of `capture_provenance` from `scope_aware_fusion.py`: 19 of 20
isolation/audit tests pass and that one fails. This was observed during R01;
R02 does not change either file or rewrite the V2-10 manifest/audit boundary.
It needs a separately reviewed V2-boundary decision, not a quiet test edit.

## R03 review queue

R03 correction 7 is complete locally and awaits a fresh Sol review, followed
by Astra. It collects every exact configured inessive form, direct market
mention, and unknown-place candidate before selecting a target. Exactly one
nonconflicting market with no unknown competition can replace prior context.
Conflicts and strong unknown residence places stay standalone; ambiguous or
unsupported lowercase place-shaped turns keep context but use `unresolved`
provenance. The capture/audit guard remains fail-closed. This does not infer a
directory target from the session country, modify frozen evaluation content, or
start R04.

## Release state

No network, AWS, paid model, deployment, merge, push, reindex, dependency
installation or frozen-pack modification occurred. R02 is accepted locally,
but the V2 worktree is not a release candidate until later milestones supply
the required capture, answer-quality evidence and combined integration review.
