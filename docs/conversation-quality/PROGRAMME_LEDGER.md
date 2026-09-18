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
| A | References: "the other one" clarifies; "the first one" resolves; ordinary words untouched; unsafe requests reach governance; no history read for standalone messages | `app/orchestrator/reference_resolution.py`, `config/reference_vocabulary.py`, hook in `_handle_chat` | test_reference_resolution, test_reference_e2e, test_followup_state_e2e (A7 passes) | implemented; coordinator probes; Fable combined review running | "And the other country?" verified downstream: it retrieved standalone with no target (no silent guess) but got no clarification. FIXED at `5019d64` (English "and/or/so/then" added as non-content tokens) and pinned. A second resolver exists in V2 (R03 Finnish); reconcile at R04 | coordinator | R04 |
| B | Multilingual multipart fields | `config/directory_field_vocabulary.py`, `utils/directory_fields.py` | test_multilingual_fields and others | implemented; Fable pending | eligibility + waiting period and qualification amount + period are policy text, out of this module; free-delivery threshold has no field key; compounds and Finnish gradation missed; restored fields keep English labels | coordinator | verify configured-language list against config; record gaps |
| C | Timing stages | `numeric_grounding_validator.py`, `config/timing_stage_vocabulary.py` | test_timing_stage_* | implemented; Fable pending | multi-stage source sentences are unclassified (conservative); exact-word cues only | coordinator | recheck the multi-stage limit |
| D | Fragment preservation | `utils/sentence_spans.py`, evidence_contract, builder, directory_fields, validator | test_fragment_*, test_sentence_spans | implemented; Fable pending | label-anchored editors spot-probed only | coordinator | confirm the reverted round-1 patch has not returned |
| E | Dependency truthfulness and metrics | `record_dependency_unavailable` (DependencyUnavailable{component, availability}); shared `_dependency_unavailable_response`; `_retrieve_or_dependency_response`; alarm spec (not deployed) | test_dependency_* (the 3 wiring xfails flipped) | implemented (`b739f63`); Fable combined review running | Lane E's own flag withdrawn for R02's `availability`; R02's two routing sites must call the shared builder at R11; C901 cleared | coordinator | R11 combine |
| F | Contact completion | `app/response/contact_completion.py` plus the orchestrator hook | test_contact_completion_* | implemented; Fable pending | negated recommendations still match; nine-language table not natively reviewed | coordinator | verify citations and multilingual rendering |
| G | Test integrity | pytest.ini (4 suites), collection-integrity and label tests, A1 rewrite, COVERAGE.md | test_collection_integrity, test_module_docstring_labels | implemented; Fable pending | COVERAGE.md predates the A, C, D and F integrations | coordinator | refresh coverage; review each xfail and skip |
| X1 | Message-language change without the selector | none | - | - | decision doc written (`phase2/X1_LANGUAGE_SWITCH_DECISION.md`); recommends answer-only switching, with source eligibility never changing | user | **blocked**: product decision (approval 6) |
| X2 | Typos and malformed spacing | existing typo_safety (Codex), `_normalize_malformed_spacing` | pack TYPO-001/002 are needs-live | - | offline proof limited | - | inventory existing controls |
| X3 | Direct answers, unanswered part, no filler or unnamed "they" | prompt rules (Phase 1) | prompt-structure tests only | Phase 1 Fable reviewed wording | needs live | - | blocked on live eval (R12) |

## Codex retrieval backlog

| ID | Requirement | Current evidence | Review | Gap | Next |
|---|---|---|---|---|---|
| R01 | Baseline reconciliation | CURRENT_STATUS.md | complete locally | - | superseded by this ledger for current state |
| R02 | Outage contract: available/degraded/unavailable | V2 `RetrievalAvailability`, orchestrator routing, evidence.py | Sol approved; Astra approved with limitations at `fcecd93e…` | provider health is measured before final approval; not yet combined with Lane E | combine once with Lane E |
| R03 | Context-to-capture, Finnish follow-ups | C7 snapshotted byte-for-byte to `askvera-v2-work` `e3b399a` (68 files, manifest, digest `9101…` re-verified); correction 8 on `v2/r03-c8-earned-trust-20260918` | **Fable on C7: NEEDS CORRECTION**. B1 and B2 closed as stated, but multi-word direct markets ("United States") are not collected, so they still resolve with trusted provenance (blocker); illative/elative forms keep the prior market as trusted (should-fix); negation ignored; dead accented inessive keys | 7 corrections to one function, so the design was reassessed: earned trust, one decision, whole-message evidence | C8 in progress; then fresh Fable |
| R04 | One reference-resolution interface | not started; A7 request filed | - | two resolvers exist (Lane A, V2 Finnish) | design once R03 closes |
| R05 | Fusion, eligibility, identity | V2-09/V2-10 accepted with limits | historical | isolation allowlist failure (`capture_provenance`); alias collisions (below) | audit |
| R06 | Diagnose remaining misses | `phase2/R06_DIAGNOSIS.md` (desk trace; no code changed) | coordinator spot-check: the Norway numbers match the raw capture | Norway: a GENUINE current miss. The country mention triggers directory protection (sponsoring-081-norway 10.10 vs policy 18.02-i 1.40); moved to R05 as N6. Tanzania/Finland: capture-tool artefacts (the old runner ignored turns). HK/Ghana: V2-09 plain RRF demotion, already gated. P001, P078, P091, P104 already fixed on the candidate. P068 and P167/168/170 unresolved; capture requests written. No source-document defects | implemented (diagnosis); R05 fix for N6; captures go to R09 |
| R07 | Evidence selection and completeness | - | - | - | after R06 |
| R08 | Production-compatible V2 adapters | `phase2/R08_V2_ADAPTER_INVENTORY.md` | inventory done (read-only) | EVERY V2 module takes synthetic inputs only, with zero live wiring (verified by grep); the one live exception is providers.py `_runtime_scope_intent`/`_authorized_policy_market` (pure metadata). Production already covers reference resolution, scope authorization and the composition contract, so REUSE those and add adapters only for V2's genuinely new scope-aware fusion (production fusion is weighted-additive `_merge_hits`, not RRF). No V2 flag exists; the package is stdlib-only and I/O-free, so disabled means zero live calls by construction | adapters after R05; decide fusion-only adoption |
| R09 | Capture preparation | capture/finalizer scripts (fail-closed on multi-turn) | - | application-path capture with stored turns not built | prepare, zero-call preflight |
| R10 | Authorized capture | - | - | - | **blocked** (approval) |
| R11 | Clean integration | Codex-conflict probe: 2 hunks at the retrieve() site (pre-Phase-2 measurement) | - | - | after E and R03 |
| R12 | Final evaluation and release prep | - | - | - | **blocked** (approval) for the paid run; prep is local |

## New findings (coordinator, 15:5x)

| ID | Finding | Evidence | Severity | Owner | Next |
|---|---|---|---|---|---|
| N1 | `config/market_name_aliases.json` (CLDR-generated) lists **"Tai"** for Thailand. Every Finnish message containing "tai" ("or") gets directory target Thailand, e.g. "Voinko maksaa kortilla tai käteisellä?" → {Thailand}. Present on `origin/main`, so in production | `_directory_target_country_names` probe on the candidate and on V2 | high | R05 | **implemented** (`b2853b7`, merged `fb6f54f`): a closed-class function word is never used as an alias; the guard runs in `services/market_config.py`; the CLDR file is untouched. Audit of 3,232 aliases found exactly one collision (TH "Tai"). Failing-before verified; 29 tests; exit 0. Limits: only languages with a function-word table are covered (13 of 39); a `services` module now imports `app.orchestrator` constants lazily (verified no import cycle in either order; a layering smell). Not yet independently reviewed |
| N2 | Ambiguous real nouns match markets: "mali" (hr "small"), "chile" (es "chili"), "turkey" (en) | same probe | low-medium | R05 | document; case and context heuristics only if general |
| N3 | Finnish inflected country names outside the inessive are missed, e.g. "Kenian" gets no target | same probe | medium | R05 / R04 | bounded inflection support or honest gap |
| N4 | Phase 1 `dbc6a7a` left C901 (complexity 16) on `_handle_scrubbed_chat` | flake8 | lint | Lane E | extraction |
| N5 | R03 anchor keeps the Finnish text "Tansaniassa" after resolution; the directory target is correctly {Uganda} | probe | note | R03 | disclose; lexical impact unmeasured |

## Language coverage (from real configuration)

Enabled markets configure **39** language codes: ar(10 markets), az, bg, bs,
cs, da, de(3), el(2), en(118), es(36), et, fi, fr(30), he, hr, hu(2), it(3),
ka, kk, ku, ky, lt, lv, mk, nl(2), no, pl, pt(3), ro(2), ru(5), sk, sl,
sq(3), sr(3), sr-ME, sv(2), tr, uk, uz.

| Capability | Languages covered | Everything else |
|---|---|---|
| Route copy (refusals, outage, clarification) | da de en es fi fr it nl no ru sr sv (12) | English or translated copy |
| A: reference vocabulary | en fr de nl it pt es fi no sv (10) | unchanged (no clarification) |
| B: directory-field vocabulary | en fr de nl it pt es fi no sv, plus da ru sr (13) | returns None, so nothing is stripped |
| C: timing-stage vocabulary | en fr de nl it pt es fi no nb sv | unclassified (never newly flagged) |
| F: contact recommendation | en plus 9 | nothing appended |

This is "fail conservatively", not multilingual support. Approval 7 asks for
a prioritized list.
| N6 | Norway former-FBO reapplication (a company-policy question) is crowded out by the Norway DIRECTORY record because the question names the country. Directory protection fires on a country mention alone | raw capture `ho-slp-16`: sponsoring-081-norway 10.10, then policy 18.02-i 1.40, with no policy clause in the top 30 | high | R05 | directory protection must require genuine directory/sponsoring intent plus an explicit resolved target (the brief's R05 rule) |
| N7 | The V2 isolation test is weaker than it looks: 6 V2 modules load siblings via `__import__(__package__ + ...)`, which the AST allowlist check cannot see (verified at e3b399a). Only siblings are reached, so the offline boundary itself is not breached | grep at e3b399a | medium (test integrity) | R05 | make the test see dynamic imports, allowlist the legitimate siblings, then add `capture_provenance` (R08 recommendation) |
