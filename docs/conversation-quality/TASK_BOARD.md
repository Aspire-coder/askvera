# AskVera conversation-quality task board

Coordinator: Claude Opus 5 (this session). Started 2026-09-18.
Authority: the user's direct instruction of 2026-09-18. The handoff pointers in
`docs/agent-handoffs/` are stale (Dev assignment dated 2026-09-11, status
2026-09-09) and are neither used nor edited.

## Baseline

| Name | Commit | What it is |
|---|---|---|
| B0 | `5b1d33f` | `origin/main` (PR #160 merged). |
| B1 | `d7b9747` | B0 plus four open branches, all in this project's ownership lanes, merged locally (not pushed): `fix/history-is-not-evidence-20260916`, `fix/fallback-offers-customer-care-20260916`, `fix/policy-question-not-a-claim-20260917`, `fix/income-bypass-coverage-and-market-config-20260915`. Textually clean. `income_claim_policy.py` and `config/vera_persona.py` auto-merged. Full `tests/unit` + `tests/governance` on B1 reached `[100%]` under `-x` with no failures section. (Correction: the recorded "exit 0" was `tail`'s exit code, not pytest's. The candidate run below captured pytest's own exit code.) |

**Production uncertainty.** B0 was requested for deployment on 2026-09-17, but
this session never saw a completed deploy or a live `git log` from the host.
B0 is the *intended* production state, not a verified one. B1 is ahead of
production by four unmerged branches by construction.

Candidate work diffs against B1, so each lane's own changes are reviewable
without the four pre-existing branches mixed in.

## Worktrees

| Path | Branch | Owner |
|---|---|---|
| `askvera-conv-quality` | `feat/conversation-quality-20260918` | Coordinator: integration and all `chat_orchestrator.py` edits |
| `askvera-conv-a-followup-state` | `conv/a-followup-state-20260918` | Lane A (Sonnet) |
| `askvera-conv-b-composition` | `conv/b-composition-20260918` | Lane B (Sonnet) |
| `askvera-conv-c-intent-contacts-recovery` | `conv/c-intent-contacts-recovery-20260918` | Lane C (Sonnet) |
| `askvera-conv-g-regression-pack` | `conv/g-regression-pack-20260918` | Lane G (Sonnet) |

## File ownership

**Codex-owned: never edited here.** `app/retrieval/**` (including
`opensearch_sections.py`, `section_index.py`, `providers.py`, `typo_safety.py`),
`app/experimental/**`, `scripts/ingestion/**`, `scripts/offline_retrieval_replay.py`,
the retrieval capture tools, `config/search_glossary.json`,
`config/sponsoring_directory_country_aliases.json`, `config/market_name_aliases.json`,
and the `askvera-evidence-first-v2` worktree.

Exception already in B1: `fix/income-bypass-coverage-...` edits
`app/retrieval/providers.py` (intent-classifier bypass, not ranking). It
pre-dates this project and is flagged for Codex awareness, not further edited.

**Single-writer shared file.** `app/orchestrator/chat_orchestrator.py`: the
coordinator only. Lanes that need an orchestrator change deliver a patch file
plus a failing test. They do not edit the file.

| Lane | May edit |
|---|---|
| A | new `tests/conversation/test_followup_state*.py`; `services/session.py` only for a demonstrated isolation defect |
| B | `app/prompts/templates.py`, `app/prompts/builder.py`, `app/response/quality.py`, `app/evidence_contract.py`, `app/validation/validators/numeric_grounding_validator.py`, `app/validation/validators/answer_validator.py`, new `tests/conversation/test_composition*.py` |
| C | `config/conversation_routes.json`, `config/public_contacts.json`, `utils/directory_fields.py`, `app/response/builder.py`, `services/guardrails.py`, `app/risk/**`, new `tests/conversation/test_intent*.py`, `test_contacts*.py`, `test_recovery*.py` |
| G | new `tests/conversation_pack/**` and its fixtures only. Read-only everywhere else. |

`app/prompts/templates.py` belongs to B alone. Tone (task E) moved into Lane B
for that reason.

## Tasks and acceptance criteria

Status values: `todo`, `active`, `repro-confirmed`, `no-defect-pinned`,
`implemented`, `reviewed`, `blocked`.

| ID | Task | Acceptance | Lane | Status |
|---|---|---|---|---|
| A1 | Kenya office-or-order follow-up | Kenya kept; numbers from re-retrieved source | A | no-defect-pinned. Retrieval re-run is real; answer numbers are scripted |
| A2 | "And the office hours?" | office context kept | A | no-defect-pinned (e2e) |
| A3 | Explicit new place | old place not inherited | A | no-defect-pinned (e2e) |
| A4 | Cross-conversation isolation | no state, cache identity or facts shared | A | no-defect-pinned (real memory session store) |
| A5 | Topic change | irrelevant context released | A | no-defect-pinned (e2e) |
| A6 | Language switch (selector) | topic kept, language follows | A | no-defect-pinned for deterministic text; model language needs live |
| A7 | Ambiguous follow-up | brief clarification | A | OPEN: strict xfail; Codex request `A7-unresolved-reference.md` |
| A8 | Hallucinated prior answer | cannot become evidence | A | no-defect-pinned (real validator pipeline) |
| B1 | Manager qualification completeness | concrete requirements stated | B | prompt rule; needs live |
| B2 | FBO vs Preferred Customer minimum order | both distinguished | B | prompt rule (needs live) + ROLE-CHANGE-001 deterministic guard |
| B3 | Two-part question | both parts, or gap named | B/C | IMPLEMENTED: post-processing no longer deletes a requested part (MULTIPART-001); prompt rule names the gap (needs live) |
| B4 | Delivery vs approval timing | never conflated | B | OPEN: Lane B's rule dropped to hold the prompt budget; no deterministic reproduction found |
| B5 | Adjacent-role figure loss | figure survives | B | IMPLEMENTED: numeric validator frees a plural acronym subject; wrong figures still flagged |
| B6 | Post-validator remnant | grammatical and useful | B/C | PARTIAL: decimal-time remnant ("00 am - 19.00 pm.") fixed; no general audit done |
| E1 | Natural, concise answers | direct first sentence, no filler | B | prompt rule; needs live |
| C1 | Company-identity income disclaimer | none | C | no-defect-pinned at intent and governance; model prose needs live |
| C2 | Purchase and returns guardrail misfire | none | C | no-defect-pinned at intent and governance; model prose needs live |
| C3 | Unsupported fact invented | honest limitation | C | diagnosis only: no clear workbook case (`laneC-c3-c4-diagnosis.md`) |
| C4 | Supported fact refused | answered | C | diagnosis only: points to retrieval/evidence approval (Codex); several cited cases were fixed before this project |
| C5 | Five failure kinds worded distinctly | accurate per kind | C/coord | PARTIAL: Bedrock timeouts and escaping retrieval/embedding errors fixed; a real OpenSearch outage is still reported as missing evidence (Codex request `C5-retrieval-outage-masked-as-no-evidence.md`) |
| D1 | Verified contact presentation | right type/country; exact; none invented | C | no-defect-pinned (6 tests) |
| F1 | Recovery | coherent and honest | C/coord | PARTIAL: dependency failures as C5; unnamed-"they" handled as a prompt rule (needs live); empty answer and central-claim rejection already routed to fallback (not re-audited) |
| G1 | Conversation regression pack | all categories, honest labels | G | IMPLEMENTED: 27 cases; one expectation corrected; one finding fixed; premise-only checks now report as skips |

## Initial Priority A reproduction (coordinator, query layer, 2026-09-18)

Probed `_build_retrieval_query` against realistic history (a real Kenya
contact answer, not the "Earlier answer." stub the existing tests use):

- A1, A2: Kenya kept. PASS at the query layer.
- A3: "What about Uganda?" drops Kenya and names Uganda. PASS. The anchor reads
  "What is the phone number for Forever? What about Uganda?", which is awkward
  but correct.
- A4, A5: standalone. PASS. `test_two_sessions_with_different_targets_never_share_cache_identity` already pins cache isolation.
- A6: French and Spanish follow-ups keep the Kenya anchor. PASS at the query
  layer. The response language comes from the per-request widget selector
  (`body.language`). Typing in a new language without changing the selector is
  not detected, and nothing in the repo detects message language. That is a
  limitation, not a defect to fix here, because the rules prohibit new
  dependencies and require the existing language configuration.
- A7: "What about the other one?" anchors to Kenya rather than clarifying.
  Needs end-to-end judgement.
- A8: `_latest_context_anchor` uses user turns only, the prompt frames history
  as "never evidence", and the output PII scrub allows numbers only from
  sources or approved contacts. Coverage is layered but only instruction-level
  for non-numeric, non-contact claims on policy answers.
  `history_grounding_validator` (in B1) covers directory-only retrievals.

## Integration risk: Codex V2 overlaps Lanes A–C

`askvera-evidence-first-v2/app/experimental/evidence_first_v2/` contains its
own standalone-request builder (V2-02, conversation state), composer and
validation (V2-04), and fixed refusal outcomes. Astra's 02:47 advisory plans to
extend it toward "manager completeness, P001, public contacts, role-bound
figures, sponsoring versus country policy and multilingual follow-ups". That is
this project's scope.

V2 is offline and not wired into production, so there is no file conflict. If
V2 is later cut over, it would supersede the production-path changes made
here in Lanes A–C. This project deliberately improves the production path and
does not build a second state framework. The user needs to decide which path
owns composition long-term. Recorded for the final handoff; not blocking.

## Integration notes

- `pytest.ini` sets `testpaths = tests/unit`, so `tests/conversation` and
  `tests/conversation_pack` do not run by default. Run them explicitly, or
  adopt the `testpaths = tests` change on `chore/measure-real-coverage-20260917`.

## Rejected worker proposals

- Lane A's A7 patch: an English regex for "the other one" that returns a
  refusal rather than a clarification.
- Lane C's `_drop_dangling_pronoun_handoffs`: an English-only fourteenth
  post-editor that deletes the reader's next step. Moved to Lane B as a
  composition rule.

## Independent review (Fable, 2026-09-18, on a3d965f) and disposition

| # | Finding | Severity | Disposition |
|---|---|---|---|
| 1 | The retrieve() catch cannot fire for a real OpenSearch outage; the provider swallows it and it is reported as missing evidence | blocker for the C5 claim | Claim corrected. `AwsServiceError` (the embedding path) added and tested; limitation documented in code; Codex request filed |
| 2 | Bedrock failures move from HighErrorRate to HighFallbackRate, undisclosed | should-fix | Disclosed in code at both catch sites; on the user approval queue |
| 3 | A bare "hours" (a duration) kept an unrequested business-hours sentence | should-fix | Fixed: only "business/office hours" counts inside the order-size branch. Also fixed the "09.00" sentence split; tests fail before and pass after |
| 4 | Stale docs and docstrings (patch files, xfail state, board) | should-fix | Fixed |
| 5 | Needs-live cases reported PASS; premise-only checks were vacuous; ROLE-CHANGE-001 blessed an unsourced answer | note | Premise checks now skip; README states what a pass means; ROLE-CHANGE-001 scripted answer is now an honest gap |
| 6 | Prompt wording: "closing questions" vs clarification; lost "unavailable"; `never "they"` | note | "sign-off questions"; "prohibited or unavailable parts" restored; handoff rule is now "Name who to contact." (4383 chars, inside budget) |
| 7 | Unused `as exc`; A1 answer assertions are decided by the scripted model | note | Removed; A1 docstring states what it does and does not prove |

## Blockers

None.

## Approvals needed

None for offline work. Any live chatbot run, model call, deploy, merge or push
is out of scope without separate authorization.

## Tooling note

AGENTS.md asks for `graphify update .` after code changes. graphify is not
installed and `graphify-out/` does not exist. Installing it is out of bounds,
so the rule cannot apply in this session.

---

# Phase 2 (started 2026-09-18, base `3c0e6c5`; tested code `dbc6a7a`)

## New constraint found at kickoff

Codex's `askvera-evidence-first-v2` worktree now has uncommitted edits to
`app/orchestrator/chat_orchestrator.py`, `app/retrieval/opensearch_sections.py`
and `app/retrieval/providers.py`. In the orchestrator it wraps
`_build_retrieval_query` in `_build_retrieval_query_with_provenance` (around
lines 1874-1950) and puts `retriever.retrieve` inside a `try/finally` (around
lines 1030-1065). Those are the regions that A7 and C5 touch. It also adds
`import hashlib` at the top.

Rule for this phase: an orchestrator change is a **small hook calling a new
module**, placed outside those regions. At integration the coordinator
trial-applies Codex's orchestrator diff (read from its worktree, never
written) onto a scratch copy of the candidate and records the real conflict
surface.

No outage contract exists in Codex's changes yet, so Lane E defines one on
the conversation side.

## Lane ownership (disjoint write sets)

| Lane | Goal | Writes (exclusive) |
|---|---|---|
| A | Unresolved references (A7) | `app/orchestrator/chat_orchestrator.py` (sole writer; hooks only), new `app/orchestrator/reference_resolution.py`, new `config/reference_vocabulary.py`, `config/conversation_routes.json` (clarification copy only), new `tests/conversation/test_reference_*.py`, `tests/conversation/test_followup_state_e2e.py` (A7 xfail flip only) |
| B | Multilingual directory fields | `utils/directory_fields.py`, new `config/directory_field_vocabulary.py`, `tests/conversation/test_intent_multipart_order_size_payment.py`, `tests/conversation/test_order_size_field_keeping.py`, new `tests/conversation/test_multilingual_fields*.py` |
| C | Timing and process stage | `app/validation/validators/numeric_grounding_validator.py`, new `config/timing_stage_vocabulary.py`, new `tests/conversation/test_timing_stage*.py` |
| D | Fragment audit | `app/evidence_contract.py`, `app/response/quality.py`, `app/response/builder.py`, `utils/inline_citations.py`, new `utils/sentence_spans.py`, other editors except B's, C's and A's files; new `tests/conversation/test_fragment_*.py`; `docs/conversation-quality/phase2/FRAGMENT_AUDIT.md`. Defects in another lane's file become a failing test plus a patch under `docs/conversation-quality/phase2/patches/` |
| E | Dependency truthfulness and observability | `app/metrics/**`, new `app/orchestrator/dependency_contract.py`, new `tests/conversation/test_dependency_*.py`, `docs/conversation-quality/codex-requests/C5-*.md`, `docs/conversation-quality/phase2/DEPENDENCY_ALARM_SPEC.md`; orchestrator wiring as a patch |
| F | Contact completion | new `app/response/contact_completion.py`, new `tests/conversation/test_contact_completion*.py`; orchestrator wiring as a patch; `utils/directory_fields.py` and `config/public_contacts.json` read-only |
| G | Test and measurement integrity | `pytest.ini`, `Makefile`, `tests/conversation_pack/**`, existing Phase 1 files `tests/conversation/test_{composition_*,contacts_*,intent_company_*,intent_dependency_*,followup_state_e2e (except A7)}.py`, `docs/conversation-quality/phase2/COVERAGE.md` |
| Coordinator | Integration | `app/prompts/templates.py`, `config/settings.py` (`PROMPT_VERSION`), `tests/unit/test_codex_conversation_tone.py` and `tests/unit/test_bedrock.py` pins, applying patches, all `docs/conversation-quality/*.md` except lane-owned ones |

Never written: `app/retrieval/**`, `app/experimental/**`, `docs/evidence_first_v2/**`,
`scripts/evidence_first_v2/**`, `tests/evidence_first_v2/**`, the
`askvera-evidence-first-v2` worktree, frozen evaluation content.

## Phase 2 progress

| Lane | Status | Criteria done | Tests | Limitations |
|---|---|---|---|---|
| A | active | 0 | - | - |
| B | active | 0 | - | - |
| C | active | 0 | - | - |
| D | active | 0 | - | - |
| E | active | 0 | - | - |
| F | active | 0 | - | - |
| G | active | 0 | - | - |

Phase 2 complete: 0% (0 of 7 lanes integrated; Fable review pending).
