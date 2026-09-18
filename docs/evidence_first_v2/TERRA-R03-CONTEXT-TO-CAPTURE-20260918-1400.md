# Terra handoff - R03 context-to-capture

Date: 2026-09-18  
Scope: local and offline only.  
Next owner: fresh Sol review, then Astra. Do not start R04.

## Boundary and starting state

This R03 correction preserves the accepted R02 snapshot and all unrelated
dirty V2 and Claude work. It does not edit the frozen held-out fixture,
isolation allowlist, provider availability work, any Claude worktree, or any
AWS-facing configuration.

## Trace and reproduction

### Tanzania follow-up

The frozen Tanzania case stores a first user turn about foreign-resident FBO
bonuses and a final turn, `And what about FBOs who live there?`. Both older
retrieval-only artifacts (`retrieval-capture-20260918.json` and its `-r3`
successor) recorded the final question alone with `context_resolution: null`.

The cause is the old retrieval-only runner, not the application path: it loops
over `case["question"]` and calls `OpenSearchSectionProvider.retrieve` once. It
does not read `case["conversation"]`, construct session history, invoke the
orchestrator, or attach runtime context provenance. It therefore cannot make
a truthful multi-turn capture.

The application path already reads the session history, creates a contextual
query, passes that exact query to the provider, and attaches an opaque
`prior_user_turn_id` to rank-list capture. With real Tanzania history the
contextual query retains Tanzania and the current local-resident question; the
scope query uses that context. With no history it stays standalone. A new,
unconfigured place stays standalone rather than borrowing Tanzania or the
widget/session country.

### Finland follow-up

The Finnish frozen case likewise reached the old runner as its final question
alone. Separately, the live local orchestrator had a real defect: the
configured Finnish third-person follow-up form `Entä jos hän...` was treated as
a new long question, so it discarded the prior 36-month inactivity turn and
the subsequent Manager-role qualification.

## Correction

1. `capture_read_only_retrieval.py` and its checkpoint finalizer now reject
   every case with non-empty stored conversation before loading configuration,
   creating clients, or making a request. A retrieval-only artifact can no
   longer silently claim to represent a multi-turn case. A future capture for
   those cases must use the application pipeline that replays stored turns.
2. `AIOrchestrator` now recognizes the narrow configured Finnish anaphoric
   form `Entä jos hän/hänen ...`. It is grammar-bound, does not name a country,
   role, or topic, and requires history. It does not turn a new standalone
   `Entä jos haluan...` question into a follow-up.

No country-specific behavior was added. The existing current-turn market
replacement, unknown-place guard, policy-scope rule, and session isolation
remain authoritative.

## Resident scope limitation

R03 does not rewrite a previous "foreign resident" phrase into a local-
resident claim. That would be an unsafe, language-specific semantic rewrite.
Instead, with actual user history, retrieval receives both the prior foreign
question and the current "live there" reference, retains the resolved
Tanzania target, and leaves the answer/evidence stage to distinguish the two
source-supported resident conditions. Without history, no target or resident
scope is inferred.

## Changed paths

- `app/orchestrator/chat_orchestrator.py`
- `scripts/evidence_first_v2/capture_read_only_retrieval.py`
- `scripts/evidence_first_v2/finalize_read_only_capture.py`
- `tests/evidence_first_v2/test_r03_context_capture.py`
- `docs/evidence_first_v2/CURRENT_STATUS.md`
- this handoff

## Verification

| Check | Result |
| --- | --- |
| Initial R03 controls | 3 failed, exit 1: missing truthful-capture guard; Finnish history was dropped; one Tanzania assertion expected the wrong safe query separator, while the runtime was already retaining its history. |
| R03 focused plus multilingual, market/topic, no-history, canary, and capture controls | 446 passed, exit 0 |
| R02/R03 compatibility suite | 460 passed, 1 known isolation-allowlist failure, exit 1 |
| Raw targeted flake8 | exit 1 only for established repository-wide E501, E203, C901, and E402 baseline findings in the selected legacy files |
| Targeted flake8 using the project's established baseline ignores | exit 0 |
| `git diff --check` | exit 0 |

The new R03 controls cover a stored-turn capture rejection, Tanzania
history-dependent target retention, unknown/unconfigured-place isolation, no
history, the Finnish configured-language role follow-up, and opaque
per-session provenance. Existing compatibility tests cover topic and market
changes, role changes, cross-session isolation, and capture conversion.

The single compatibility failure is the separately recorded
`scope_aware_fusion.py` relative `capture_provenance` isolation allowlist
mismatch. R03 leaves both the import and allowlist untouched.

## Stable snapshot identity

Base HEAD: `5b1d33fe37167e2a1384e47ac0fa1fe08ea3aee7`

R03 selected-file snapshot SHA-256:

`a3459346f3bf5102dd2b456e05e35314268adf7686860b3cec83c9936bcb8a14`

The digest is SHA-256 over UTF-8 canonical lines of `path`, LF, and the
lowercase SHA-256 of that file's exact bytes, with one final LF. It covers:
`app/orchestrator/chat_orchestrator.py`,
`scripts/evidence_first_v2/capture_read_only_retrieval.py`,
`scripts/evidence_first_v2/finalize_read_only_capture.py`, and
`tests/evidence_first_v2/test_r03_context_capture.py`. The canonical manifest
was 463 bytes. This is a selected dirty-worktree snapshot, not a clean commit,
release, or production identity.

## Limits and next review

- No AWS, network, OpenSearch, live model, reindex, install, push, merge, or
  deployment occurred.
- The old retrieval-only artifacts remain historical, first-turn-only evidence
  for their multi-turn rows. They are not retroactively repaired.
- Local tests prove context propagation and capture truthfulness, not live
  ranking, answer quality, resident-condition interpretation, or release
  readiness.
- Send this exact snapshot to a fresh Sol review, then Astra final review.
  Stop after review; R04 remains paused.
