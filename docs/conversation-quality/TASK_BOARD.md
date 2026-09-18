# AskVera conversation-quality task board

Coordinator: Claude Opus 5 (this session). Started 2026-09-18.
Authority: the user's direct instruction of 2026-09-18. The handoff pointers in
`docs/agent-handoffs/` are stale (Dev assignment dated 2026-09-11, status
2026-09-09) and are neither used nor edited.

## Baseline

| Name | Commit | What it is |
|---|---|---|
| B0 | `5b1d33f` | `origin/main` (PR #160 merged). |
| B1 | `d7b9747` | B0 plus four open branches, all in this project's ownership lanes, merged locally (not pushed): `fix/history-is-not-evidence-20260916`, `fix/fallback-offers-customer-care-20260916`, `fix/policy-question-not-a-claim-20260917`, `fix/income-bypass-coverage-and-market-config-20260915`. Textually clean. `income_claim_policy.py` and `config/vera_persona.py` auto-merged. **Verified:** full `tests/unit` + `tests/governance` passed on B1 (`-x`, exit 0, 2026-09-18). |

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
| A1 | Kenya office-or-order follow-up | Kenya kept; numbers come from re-retrieved source, never from history | A | no-defect-pinned (e2e) |
| A2 | "And the office hours?" | office context kept | A | no-defect-pinned (e2e) |
| A3 | Explicit new place | old place not inherited | A | no-defect-pinned (e2e) |
| A4 | Cross-conversation isolation | no state, cache identity or facts shared | A | no-defect-pinned (real memory session store) |
| A5 | Topic change | irrelevant context released | A | no-defect-pinned (e2e) |
| A6 | Language switch (selector change mid-session) | topic kept, response language follows the new selection | A | no-defect-pinned (deterministic text only; model language needs live) |
| A7 | Ambiguous follow-up | brief clarification when unresolvable | A | repro-confirmed, OPEN: strict xfail; Codex request `codex-requests/A7-unresolved-reference.md` |
| A8 | Hallucinated prior answer | cannot become evidence | A | no-defect-pinned (real validator pipeline) |
| B1 | Manager qualification completeness | supported requirements stated, not "specific requirements apply" | B | todo |
| B2 | Minimum order FBO vs Preferred Customer | both distinguished when both are supported | B | todo |
| B3 | Two-part question | both parts answered, or the unestablished part named | B | todo |
| B4 | Delivery vs approval timing | never conflated | B | todo |
| B5 | Adjacent-role figure loss | a valid figure survives an adjacent role clause | B | todo |
| B6 | Post-validator remnant | still grammatical and useful | B | todo |
| E1 | Natural, concise answers | direct first sentence, no filler, no added model call | B | todo |
| C1 | Company-identity income disclaimer | "What is Forever Living Products?" gets no income disclaimer | C | todo |
| C2 | Purchase and returns guardrail misfire | no unrelated guardrail | C | todo |
| C3 | Unsupported fact invented | honest limitation | C | todo |
| C4 | Supported fact refused | answered | C | todo |
| C5 | Five failure kinds worded distinctly | scope, country restriction, missing evidence, ambiguity, dependency | C (wording) / coordinator (orchestrator wiring) | todo |
| D1 | Verified contact presentation | right type, country and topic; exact digits; no duplicate; none invented | C | todo |
| F1 | Recovery: timeout, empty, central claim rejected, empty source, unresolved "they" | coherent and honest; dependency failure kept separate from refusal | C | todo |
| G1 | Conversation regression pack | every category in the brief, paraphrases and negative controls, honestly labelled | G | implemented: 26 cases; 1 expectation corrected; MULTIPART-001 open finding (routed to Lane C) |

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

## Blockers

None.

## Approvals needed

None for offline work. Any live chatbot run, model call, deploy, merge or push
is out of scope without separate authorization.

## Tooling note

AGENTS.md asks for `graphify update .` after code changes. graphify is not
installed and `graphify-out/` does not exist. Installing it is out of bounds,
so the rule cannot apply in this session.
