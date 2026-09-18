# AskVera programme ledger

Coordinator: Claude Opus 5. Started 2026-09-18 15:47 local time, on taking
over the full remaining programme (conversation-quality Phase 2 plus Codex
R01-R12). This is the single current-state record. Older handoffs are
evidence; they are not authority.

Status vocabulary, used strictly:
- **open**: not done.
- **implemented**: code and tests exist, verified by the coordinator.
- **reviewed**: independently reviewed by a model that did not write the code.
- **live-validated**: exercised against real services.
- **blocked**: needs approval (see APPROVAL_QUEUE.md).
- **deferred**: not done, for a stated reason.

Blocked and deferred items never count as completed.

## Verified starting state (15:47-15:51)

| Item | Observed |
|---|---|
| Conversation candidate | `askvera-conv-quality`, `feat/conversation-quality-20260918`, HEAD `0336c2d`, clean |
| Lane E | worktree `askvera-p2-e-dependency`, uncommitted, agent still writing (test files touched 15:47); redirected at 15:5x onto the R02 contract |
| V2 worktree | `askvera-evidence-first-v2`, `experiment/evidence-first-v2-20260917`, base `5b1d33f`, 13 modified plus 4 untracked trees |
| V2 R03 state | files hash to the **Correction 7** snapshot `9101284889a4aa074b5dec681075ae3b4539dbe4b977997b92d5db322c078bd6` (recomputed by the coordinator: "path LF sha256 LF" per file, 463 bytes). The brief's "Correction 6 rejected" is one step behind: Correction 7 (15:41) exists and awaits review |
| V2 writer activity | no V2 file changed between 15:42 and 15:51 (mtime snapshots). The Codex app server process is running but idle for this tree. To be re-checked before any V2 write |
| V2 write access | MSI\KRISH has full control. Git needs a per-command `-c safe.directory`; global config was NOT changed |
| Python | `askvera-deploy\.codex-py311-venv\Scripts\python.exe` exists |

**Working decision.** The V2 worktree is never edited in place. Later V2
work runs in a coordinator-owned worktree on a versioned branch, seeded from
an explicit allowlist of V2 files at a recorded snapshot. The original stays
byte-for-byte preserved.

## Conversation-quality Phase 2

| ID | Requirement | Implementation | Tests | Review | Gap | Owner | Next |
|---|---|---|---|---|---|---|---|
| A | References: "the other one" clarifies; "the first one" resolves; ordinary words untouched; unsafe requests reach governance; no history read for standalone messages | `app/orchestrator/reference_resolution.py`, `config/reference_vocabulary.py`, hook in `_handle_chat` | test_reference_resolution, test_reference_e2e, test_followup_state_e2e (A7 passes) | implemented; coordinator probes; Fable pending | "And the other country?" is left unchanged. Downstream retrieval behaviour is not yet verified: an unchanged message may still retrieve against the latest anchor. A second resolver exists in V2 (R03 Finnish); must reconcile at R04 | coordinator | verify downstream; R04 |
| B | Multilingual multipart fields | `config/directory_field_vocabulary.py`, `utils/directory_fields.py` | test_multilingual_fields and others | implemented; Fable pending | eligibility + waiting period and qualification amount + period are policy text, out of this module; free-delivery threshold has no field key; compounds and Finnish gradation missed; restored fields keep English labels | coordinator | verify configured-language list against config; record gaps |
| C | Timing stages | `numeric_grounding_validator.py`, `config/timing_stage_vocabulary.py` | test_timing_stage_* | implemented; Fable pending | multi-stage source sentences are unclassified (conservative); exact-word cues only | coordinator | recheck the multi-stage limit |
| D | Fragment preservation | `utils/sentence_spans.py`, evidence_contract, builder, directory_fields, validator | test_fragment_*, test_sentence_spans | implemented; Fable pending | label-anchored editors spot-probed only | coordinator | confirm the reverted round-1 patch has not returned |
| E | Dependency truthfulness and metrics | Lane E in progress | - | - | must use R02's availability contract; one fallback builder; C901 on `_handle_scrubbed_chat` (complexity 16) outstanding | Lane E, then coordinator | finish, review, combine with R02 once |
| F | Contact completion | `app/response/contact_completion.py` plus the orchestrator hook | test_contact_completion_* | implemented; Fable pending | negated recommendations still match; nine-language table not natively reviewed | coordinator | verify citations and multilingual rendering |
| G | Test integrity | pytest.ini (4 suites), collection-integrity and label tests, A1 rewrite, COVERAGE.md | test_collection_integrity, test_module_docstring_labels | implemented; Fable pending | COVERAGE.md predates the A, C, D and F integrations | coordinator | refresh coverage; review each xfail and skip |
| X1 | Message-language change without the selector | none | - | - | product behaviour undefined: answer language vs source eligibility | coordinator | define behaviour first (decision doc), then implement if safe |
| X2 | Typos and malformed spacing | existing typo_safety (Codex), `_normalize_malformed_spacing` | pack TYPO-001/002 are needs-live | - | offline proof limited | - | inventory existing controls |
| X3 | Direct answers, unanswered part, no filler or unnamed "they" | prompt rules (Phase 1) | prompt-structure tests only | Phase 1 Fable reviewed wording | needs live | - | blocked on live eval (R12) |

## Codex retrieval backlog

| ID | Requirement | Current evidence | Review | Gap | Next |
|---|---|---|---|---|---|
| R01 | Baseline reconciliation | CURRENT_STATUS.md | complete locally | - | superseded by this ledger for current state |
| R02 | Outage contract: available/degraded/unavailable | V2 `RetrievalAvailability`, orchestrator routing, evidence.py | Sol approved; Astra approved with limitations at `fcecd93e…` | provider health is measured before final approval; not yet combined with Lane E | combine once with Lane E |
| R03 | Context-to-capture, Finnish follow-ups | Correction 7 at `9101…` | Sol/Astra review never completed; **Fable review started** | two blockers claimed fixed; coordinator reproduction: B1 now standalone, B2 `unresolved` with no prior-turn id, `pseudougandassa` not Uganda | close on Fable verdict |
| R04 | One reference-resolution interface | not started; A7 request filed | - | two resolvers exist (Lane A, V2 Finnish) | design once R03 closes |
| R05 | Fusion, eligibility, identity | V2-09/V2-10 accepted with limits | historical | isolation allowlist failure (`capture_provenance`); alias collisions (below) | audit |
| R06 | Diagnose remaining misses | laneC-c3-c4-diagnosis.md leads | - | several leads (P001, P068, P104) were fixed before Phase 1; needs current tracing | trace |
| R07 | Evidence selection and completeness | - | - | - | after R06 |
| R08 | Production-compatible V2 adapters | V2 experimental package | - | synthetic vs real inventory missing | after R05 |
| R09 | Capture preparation | capture/finalizer scripts (fail-closed on multi-turn) | - | application-path capture with stored turns not built | prepare, zero-call preflight |
| R10 | Authorized capture | - | - | - | **blocked** (approval) |
| R11 | Clean integration | Codex-conflict probe: 2 hunks at the retrieve() site (pre-Phase-2 measurement) | - | - | after E and R03 |
| R12 | Final evaluation and release prep | - | - | - | **blocked** (approval) for the paid run; prep is local |

## New findings (coordinator, 15:5x)

| ID | Finding | Evidence | Severity | Owner | Next |
|---|---|---|---|---|---|
| N1 | `config/market_name_aliases.json` (CLDR-generated) lists **"Tai"** for Thailand. Every Finnish message containing "tai" ("or") gets directory target Thailand, e.g. "Voinko maksaa kortilla tai käteisellä?" → {Thailand}. Present on `origin/main`, so in production | `_directory_target_country_names` probe on the candidate and on V2 | high | R05 | general guard: an alias equal to a closed-class function word in a configured language must not match; audit all aliases |
| N2 | Ambiguous real nouns match markets: "mali" (hr "small"), "chile" (es "chili"), "turkey" (en) | same probe | low-medium | R05 | document; case and context heuristics only if general |
| N3 | Finnish inflected country names outside the inessive are missed, e.g. "Kenian" gets no target | same probe | medium | R05 / R04 | bounded inflection support or honest gap |
| N4 | Phase 1 `dbc6a7a` left C901 (complexity 16) on `_handle_scrubbed_chat` | flake8 | lint | Lane E | extraction |
| N5 | R03 anchor keeps the Finnish text "Tansaniassa" after resolution; the directory target is correctly {Uganda} | probe | note | R03 | disclose; lexical impact unmeasured |
