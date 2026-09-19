# Live validation prep: R10 capture + B0-vs-candidate paired run

Date: 2026-09-19. Preparation only. Nothing in this document, and nothing run
while preparing it, is a live capture, a live model call, or an AWS/
OpenSearch/Bedrock/network call of any kind. This worker's write scope is
this file and `docs/conversation-quality/phase3/manifests/*.json`; it made
zero external calls.

Worktree: `askvera-live-prep`, branch `cx/live-prep-20260919`, based on
`1599757` (unchanged; this worker only added files, it did not rebase or
merge).

## (a) What each live run would measure

### #8: R10 authorized capture (`APPROVAL_QUEUE.md` item 8, decided
"Approved, sequenced")

Runs `scripts/capture_application_path.py` against a real multi-turn
manifest through the actual `AIOrchestrator.handle_chat` path, with stored
prior turns seeded into the session memory backend exactly as production
would store them. This measures retrieval and answer *mechanism* on real
multi-turn journeys -- the five cases R06 diagnosed as broken by the old
retrieval-only capture (`docs/conversation-quality/phase2/R06_DIAGNOSIS.md`,
"Capture requests for R09/R10") specifically need this path because the old
capture ignored stored turns and evaluated follow-up questions as if they
were first turns.

### #2: paired B0-vs-candidate run (`APPROVAL_QUEUE.md` item 2, decided
"Approved, sequenced")

The only way to measure prompt-only rules and live model prose -- everything
`tests/conversation_pack/README.md` calls `needs_live`: whether the model
actually composes a two-part answer, withholds an unrelated disclaimer,
switches answer language correctly, or honestly states an evidence gap
instead of inventing a figure. Per `R12_ACCEPTANCE_THRESHOLDS.md`, this is a
**paired** run: identical request text/history/country/language/role in
both B0 (`origin/main` `5b1d33f`) and the candidate, each case run 3 times
per side at production temperature, majority-reported with disagreement
shown.

### Needs-live cases found in the repo

- `tests/conversation_pack/cases.json` -- the Lane G regression pack's
  manifest. `needs_live: true` cases (with `needs_live_reason`) are listed in
  `tests/conversation_pack/README.md`'s "Full needs-live list" table:
  `US-POLICY-001`, `US-POLICY-002`, `LANGUAGE-SELECTOR-SWITCH-001`,
  `TYPO-001`, `TYPO-002`, `UNKNOWN-001`, `UNKNOWN-002`,
  `GUARDRAIL-MISFIRE-001/002/003`.
- `tests/conversation_pack/cx/cases.json` -- the CX pack's 80 cases
  (`docs/conversation-quality/phase3/CX_LANE6_EVALUATION.md`). 30 are
  currently `xfail(strict=True)` behind 5 requirement-level flags, each
  blocked by a genuine product defect or gap (P1-P4, listed in that file),
  not something a live run alone would fix -- but a live run is still the
  only way to see the actual delivered model prose for the requirements that
  already pass their offline/flag checks (`direct_answer_first`,
  `partial_answer`, `contact_escalation`, `supported_only_suggestions`,
  `conversation_repair`, `typo_tolerance`, `confidence_aware_language`,
  `answer_language_parity`).

### The 178-case US workbook: found, but only in a temporary scratchpath

**Update, 2026-09-19 (coordinator review of `62d51c2`):** the workbook
exists. It was not checked into this repository or worktree -- the original
repo-wide search (below) correctly found nothing on disk under either
`askvera-live-prep` or the parent `enterprise-chatbot` directory -- but it
does exist in this session's **temporary** scratchpad, alongside the source
policy text it grades against:

- `C:\Users\KRISH\AppData\Local\Temp\claude\C--Users-KRISH-Downloads-Chatbot-Archives-enterprise-chatbot-askvera-deploy\7dd16586-6849-4f97-ab21-4302b395e5a1\scratchpad\us_testing_cases.md`
  (178 graded cases; 2,596 lines)
- `C:\Users\KRISH\AppData\Local\Temp\claude\C--Users-KRISH-Downloads-Chatbot-Archives-enterprise-chatbot-askvera-deploy\7dd16586-6849-4f97-ab21-4302b395e5a1\scratchpad\us_policy.txt`
  (the source policy text the workbook grades against; 1,573 lines)

Per the coordinator's explicit instruction, **neither file was copied into
this repository.** This scratchpad is session-temporary; where the workbook
should live permanently is the user's decision, not this worker's (see (d)
item 6).

`R12_ACCEPTANCE_THRESHOLDS.md` ("Stage 2") and `APPROVAL_QUEUE.md` item 2
both call for Stage 2 to re-grade "the 178-case US workbook... against the
source, not against old workbook output." The filename is named directly in
`docs/conversation-quality/codex-requests/laneC-c3-c4-diagnosis.md` line 3
(`us_testing_cases.md`, "178 graded cases, all `RESULT: None` -- ungraded by
a human yet"), and is also referenced (never contents-quoted) by
`tests/conversation_pack/README.md`, `docs/conversation-quality/phase2/
R06_DIAGNOSIS.md`, `docs/conversation-quality/phase2/COVERAGE.md`,
`docs/conversation-quality/TASK_BOARD.md`, `docs/conversation-quality/
HANDOFF.md`, and `docs/AWS_CLEANUP_TRACKER.md`.

#### Format (read directly, from the scratchpad path above)

One entry per case, Markdown, in this exact shape:

```
### P<NNN> | <category letter>. <category name> | <severity> | sec <policy section reference(s)>
Q: <the question text>
MUST: <the fact(s) the answer must contain, or "None">
MUST NOT: <the fact(s)/claim(s) the answer must never contain, or "None">
ACTUAL: <the model's actual delivered answer text, already captured -- possibly
  multi-paragraph, with Markdown formatting preserved>
RESULT: None | FAIL TYPE: None | NOTES: None
```

- **178 cases**, `P001`-`P178`, confirmed by counting `### P` headers.
- **18 categories** (the letter + name after the case id), lettered A-R:
  A. The May 2026 change; B. Joining and customer status; C. Jargon a
  newcomer would not know; D. Bonus structure and levels; E. Activity and
  case credits; F. Ordering and payment; G. International sponsoring;
  H. Manager status and leadership bonus; I. Returns, refunds and buy backs;
  J. Prohibited activities; K. Websites and online selling; L. Legal and
  confidentiality; M. Termination, death and divorce; N. Not in the
  document; O. Gaps and contradictions; P. Cross-document precedence;
  Q. High-stakes and emotional framing; R. Compliance-sensitive requests.
- **Severity**: `Critical` (81 cases), `High` (70), `Medium` (27).
- **`sec`**: one or more references into `us_policy.txt`'s own section
  numbering (e.g. "sec 1.01(a)", "sec Cover page, footer").
- **`ACTUAL`**: this is *already a captured answer* from some prior run of
  the application (not this manifest's capture) -- it is the thing to be
  graded, not a fixture to seed.
- **`RESULT` / `FAIL TYPE` / `NOTES`**: all 178 rows currently read
  `RESULT: None | FAIL TYPE: None | NOTES: None` -- confirmed by grep, zero
  exceptions. **No case in this workbook has been graded by a human yet.**
  This is the grading step R12 Stage 2 calls for ("re-graded against the
  source, not against old workbook output") -- i.e. Stage 2 is not just
  reading these `ACTUAL` values as ground truth; it re-runs each question
  live (both B0 and candidate) and grades the *new* answers against
  `us_policy.txt`, using this workbook's `Q`/`MUST`/`MUST NOT`/`sec` columns
  as the graded rubric, not its stale `ACTUAL` column.

#### How grading works

Each row is a self-contained rubric: the question (`Q`), what a correct
answer must state (`MUST`), what it must never state (`MUST NOT`), and the
exact source section(s) that support the `MUST`/`MUST NOT` claims (`sec`).
A grader (human, per R12's Stage 1 criterion 5 and Stage 2's re-grading
requirement) reads a live-captured answer to the same `Q` against
`us_policy.txt`'s cited section(s) and records a verdict -- this workbook's
own `RESULT`/`FAIL TYPE`/`NOTES` columns are exactly where that verdict
would be written, but they are all still `None` today.

#### How a paired run would consume it

1. Build a manifest (R09 schema) from the workbook's 178 `Q` values as
   `message` (first-turn, no stored `turns`, since the workbook's questions
   are standalone), with `expectations` populated from each row's `MUST`/
   `MUST NOT`/`sec` (not the stale `ACTUAL` text) -- this is real
   source-reviewed expectations content, not invented, so it satisfies (d)
   item 1's requirement directly for these 178 cases once someone does the
   transcription.
2. Run that manifest through `scripts/capture_application_path.py` with
   `--capture-final-answer`, once against B0's code identity and once
   against the candidate's, 3x each per R12's paired-run contract.
3. Grade each new `final_answer.answer` against the same row's `MUST`/
   `MUST NOT`/`sec`, exactly as a human would have filled in the workbook's
   own `RESULT`/`FAIL TYPE`/`NOTES` columns -- but against the *live*
   answer, not the workbook's captured `ACTUAL` text.
4. Feed those per-case verdicts into R12 Stage 2's metrics table (factual
   support, country/role correctness, citation quality, etc.), separately
   from the CX pack's `needs_live` cases in (a) -- the two sets are
   complementary, not overlapping (this workbook is 178 pre-May-2026-aware
   US policy questions; the CX pack's `needs_live` cases are the
   conversation-mechanism-shaped ones: language switch, typos, guardrail
   misfires).

None of this was built by this worker -- the manifest, the grading, and the
paired-run comparison are all still to be done (see (d) items 4 and 6). This
section only documents the format and the consumption path so the
coordinator does not have to rediscover it.

#### Original NOT-FOUND note (superseded above, kept for the record)

A repo-wide filename search (`find . -iname "us_testing_cases*"`), run from
both this worktree and the parent `enterprise-chatbot` directory, found no
such file anywhere on disk -- correct as far as it went, since the file was
never in either directory tree; it turned out to be reachable at the
session scratchpad path above instead, which is outside both directories
and expires with the session.

## (b) Exact commands, with caps and a placeholder approval id

**For the coordinator to post to the user -- not run here.** The manifest
path below is the draft this worker built
(`docs/conversation-quality/phase3/manifests/r10_first_manifest_DRAFT.json`,
SHA-256 `c8419690ff55894d0655df3b928b98f109038d217dcc7a4b23bca66df0af5bcb`,
75 cases, rebalanced 2026-09-19 per coordinator review of `62d51c2` -- see
"Manifest built by this worker" below for the language breakdown). Real
per-call unit prices must replace the illustrative ones below before this is
posted for real approval (see (c)); `<APPROVAL_ID>` and `<CANDIDATE_SHA>`
are placeholders, never filled in by this worker.

### R10 capture (item 8)

```
<PYTHON> scripts/capture_application_path.py \
  --manifest docs/conversation-quality/phase3/manifests/r10_first_manifest_DRAFT.json \
  --out docs/conversation-quality/phase3/manifests/r10_first_manifest.checkpoint.jsonl \
  --i-have-approval <APPROVAL_ID> \
  --max-calls 1875 \
  --max-cost <REAL_COST_CAP> \
  --unit-price retrieval=<REAL_PRICE> \
  --unit-price embedding=<REAL_PRICE> \
  --unit-price planner_or_translation=<REAL_PRICE> \
  --unit-price selector=<REAL_PRICE> \
  --unit-price reranker=<REAL_PRICE> \
  --unit-price generation=<REAL_PRICE>
```

`--max-calls 1875` is this manifest's own preflight ceiling (see (c)); the
coordinator may set it lower. A resumed run after an abort adds `--resume`
and must reuse the same `--i-have-approval` value (the script refuses to mix
approvals in one checkpoint -- `validate_resume`,
`scripts/capture_application_path.py`).

### Paired B0-vs-candidate run (item 2)

This worker found no existing single "paired run" script in this worktree;
`R12_ACCEPTANCE_THRESHOLDS.md` specifies the comparison contract (identical
inputs, 3 runs per side, majority-reported) but the runner itself is outside
this worker's write scope to build. The coordinator's command needs, at
minimum, two capture-application-path-shaped runs -- one against B0's code
identity, one against the candidate's -- over the same needs-live cases
listed in (a), each repeated 3x, with the same cap discipline:

```
# Baseline (B0, origin/main 5b1d33f) -- checked out separately, not in this worktree
<PYTHON> scripts/capture_application_path.py \
  --manifest <needs-live-cases-manifest> \
  --out <b0-checkpoint>.jsonl \
  --i-have-approval <APPROVAL_ID> \
  --max-calls <N> --max-cost <REAL_COST_CAP> \
  --unit-price ... --capture-final-answer

# Candidate (<CANDIDATE_SHA>, this worktree's eventual successor)
<PYTHON> scripts/capture_application_path.py \
  --manifest <needs-live-cases-manifest> \
  --out <candidate-checkpoint>.jsonl \
  --i-have-approval <APPROVAL_ID> \
  --max-calls <N> --max-cost <REAL_COST_CAP> \
  --unit-price ... --capture-final-answer
```

`--capture-final-answer` is required for this comparison (off by default)
since Stage 2 grades the delivered answer text itself, not just retrieval
diagnostics. The `<needs-live-cases-manifest>` would need to be built in the
R09 schema from the `needs_live` cases enumerated in (a) plus the 178-case
workbook once it is located -- that manifest does not exist yet and is a
prerequisite this document flags, not one it builds (see (d)).

## (c) Preflight output (zero calls, run from this worktree)

Confirmed from the code before running: `--preflight` (`scripts/
capture_application_path.py`, `main()`) calls only `load_manifest` and
`preflight_report`, both pure/offline (`load_manifest` only reads and
`json.loads`s the manifest file; `preflight_report` only counts cases and
multiplies by fixed per-case ceilings). Neither imports anything under
`app/`, `services/`, or `config/`, and neither constructs any client. Command
run:

```
<PYTHON> scripts/capture_application_path.py \
  --manifest docs/conversation-quality/phase3/manifests/r10_first_manifest_DRAFT.json \
  --preflight \
  --unit-price retrieval=0.0002 --unit-price embedding=0.0001 \
  --unit-price planner_or_translation=0.001 --unit-price selector=0.001 \
  --unit-price reranker=0.0 --unit-price generation=0.003
```

(The `--unit-price` values above are this worker's own illustrative
placeholders, not real prices -- flagged per (d).) Output:

```json
{
  "case_count": 75,
  "cases_per_split": {"development": 61, "evaluation": 14},
  "cost_envelope": {
    "embedding": 0.03, "generation": 0.225,
    "planner_or_translation": 0.15, "reranker": 0.0,
    "retrieval": 0.24, "selector": 0.075, "total": 0.72
  },
  "manifest_sha256": "c8419690ff55894d0655df3b928b98f109038d217dcc7a4b23bca66df0af5bcb",
  "max_calls_per_case_by_category": {
    "embedding": 4, "generation": 1, "planner_or_translation": 2,
    "reranker": 1, "retrieval": 16, "selector": 1
  },
  "max_calls_total": {
    "embedding": 300, "generation": 75, "planner_or_translation": 150,
    "reranker": 75, "retrieval": 1200, "selector": 75, "total": 1875
  }
}
```

75 cases (61 development, 14 evaluation) x 25 calls/case ceiling = 1875
total calls -- up from the earlier 43-case draft's 1075 after the
2026-09-19 multilingual rebalance (coordinator review of `62d51c2`) added
32 non-English/duplicate cases. At the illustrative unit prices above, the
cost envelope totals **$0.72** -- real prices will change this number; the
coordinator must recompute with real `--unit-price` values before posting an
approval request.

## (d) Human steps still needed before any run

1. **Expectations must be written from source documents.** Every one of the
   75 cases in `r10_first_manifest_DRAFT.json` has
   `"expectations": "TO_BE_WRITTEN_BY_SOURCE_REVIEWED_HUMAN"` -- confirmed
   the manifest validator accepts this (any JSON value is accepted for
   `expectations`; `load_manifest` only checks the key is present). No
   expectation content was invented by this worker. A source-reviewed human
   must replace every placeholder with real expectations copied from
   `us_policy.txt` and the directory/contact fixtures, per
   `R09_CAPTURE_PLAN.md`'s schema table, before grading (not before
   *capture* -- capture itself never reads `expectations`; `_runtime_fields`
   strips it). Non-English cases need their expectations written against the
   same English-language source facts -- the source documents themselves are
   not multilingual, only the question/answer are.
2. **Native-speaker copy review**, per `CX_LANE4_LOCALIZATION.md`'s "Review
   status" section: all 11 non-English `conversation_routes.json` locales
   added by Lane 4 (the CX message keys, `field_label_*` keys, and the seven
   added `bedrock_error` entries for `it da fi no sr sv ru`) are Lane 4's own
   translation and have **not** been reviewed by a native speaker of any of
   those languages. After the 2026-09-19 rebalance this manifest now
   exercises 10 non-English languages (`es de fr fi nl it no da ru sr` --
   see the language table below); of these, French, Finnish, Spanish and
   German already have prior reviewed copy per Lane 4's own notes for at
   least some keys, but every CX fallback-state/repair/typo/switch case run
   in `nl it no da ru sr` (and the rest of the `es/fr/de/fi` copy Lane 4
   itself flags as unreviewed) still needs native review before its live
   output can be trusted as *correct*, not merely *observed*. This
   manifest's own question/message text (written by this worker, not
   Lane 4's route copy) is a separate translation surface with the same
   caveat -- it was not reviewed by a native speaker either, and should be
   treated as illustrative phrasing for a human to check, not final
   customer-facing wording.
3. **The 178-case workbook has been located** (see (a)) -- it lives at a
   session-temporary scratchpad path, not a durable one. See item 6 below;
   Stage 2 cannot run against a path that disappears when this session ends.
4. **The needs-live-cases manifest for the paired run (#2) does not exist
   yet** -- see (b); it needs to be assembled from the `needs_live` lists in
   `tests/conversation_pack/README.md` plus the 178 `Q`/`MUST`/`MUST NOT`/
   `sec` rows in `us_testing_cases.md` (format and consumption path
   documented in (a)), in the same R09 schema, with its own source-reviewed
   `expectations` built from each row's `MUST`/`MUST NOT`/`sec` columns.
5. **Fault injection for `r10-19-dependency-outage-fault-injected`** needs
   its own separate environment approval (R09_CAPTURE_PLAN.md, outline row
   19) before that one case can exercise a real dependency outage; without
   it, this case will simply return whatever the dependency's real live
   state happens to be, and that is not itself informative.
6. **Move the workbook to a durable location (user decision).**
   `us_testing_cases.md` and `us_policy.txt` currently exist only at
   `C:\Users\KRISH\AppData\Local\Temp\claude\...\7dd16586-6849-4f97-ab21-
   4302b395e5a1\scratchpad\` -- a session-scoped temporary directory that is
   not part of this repository and is not guaranteed to survive past this
   session. Per the coordinator's explicit instruction, this worker did
   **not** copy either file into the repository -- where they should live
   permanently (this repo, some other durable store, etc.) is the user's
   decision, not something this worker or the coordinator should decide
   unilaterally. Until that decision is made and acted on, item 3/4 above
   (locating the workbook, building the needs-live-cases manifest from it)
   cannot be finished durably -- anyone picking this up in a future session
   will need the workbook re-supplied if the scratchpad has already expired.

## (e) Pass/fail criteria (from R12)

### Stage 1 smoke gate (`R12_ACCEPTANCE_THRESHOLDS.md`), applies to R10's ~30
outline journeys plus this manifest's CX additions

Passes only if **all** hold:
1. Zero critical regressions (unsupported factual claim, wrong country/
   scope, leaked foreign policy, missed safety refusal, invented contact).
2. Zero answers attributing a figure to the wrong role/country/process
   stage.
3. Zero dependency outages worded as missing evidence, and the reverse.
4. False refusals no worse than baseline, in absolute count.
5. Every changed answer reviewed by a person against the source (case, both
   answers, source quote, verdict recorded).

If it fails: stop, return each regression to its owning task, no automatic
re-run.

### Stage 2 expanded paired evaluation (only after Stage 1 passes)

| Metric | Acceptance |
|---|---|
| Retrieval required-section recall@5/@10/@30, best rank | no regression on any case the baseline found at rank <=10; aggregate recall@10 >= baseline |
| Final answer complete and factually supported | at least baseline; no critical unsupported claim |
| Country and role correctness | 100% on scope-sensitive cases; no foreign-policy leakage |
| Follow-up accuracy | at least baseline; "the other one" never silently guessed |
| Correct/false refusals | correct refusals no drop; false refusals no rise |
| Citation quality | at least baseline |
| Multilingual (fr, de, es, fi, nl, sv at least) | no language worse than its own baseline |
| Latency p50/p95 | p95 no more than 20% above baseline |
| Cost per answer | no more than 15% above baseline unless a reviewed quality gain justifies it |

Reporting: counts with denominators and uncertainty (e.g. "12/15 majority, 2
unstable"), never a single "quality %"; exposed development cases kept apart
from untouched evaluation cases; any paraphrase overlap disclosed; old V2-05/
V2-09 replay scores never attached to this candidate. A Stage 2 pass is a
release *recommendation* only -- merge/deploy/canary/alarms need separate
authorization (`APPROVAL_QUEUE.md` items 3/4).

## (f) B0-vs-candidate comparison procedure

1. **Same inputs, both sides.** Identical `message`, stored `turns`,
   `country`, `language`, `role`, and the same source snapshot/index
   generation, per `R12_ACCEPTANCE_THRESHOLDS.md`'s "What gets compared."
   `scripts/capture_application_path.py`'s manifest schema already enforces
   this by construction -- one manifest, run once against each code
   identity.
2. **3 runs per side**, majority-reported, disagreement shown (stochastic
   model at production temperature).
3. **Per-case metadata fields to read**, from each checkpoint row
   (`run_one_case`'s record shape in `scripts/capture_application_path.py`)
   and, where the case also runs through the CX pack, from
   `response.metadata`:
   - `outcome.kind` (`metadata["outcome"]["kind"]` on the real response) --
     the structural outcome (answer / partial_answer / clarification /
     cross_market_policy / evidence_missing / international_directory /
     personal_account / dependency_unavailable / safety_refusal); compare
     kind-for-kind between B0 and candidate before ever comparing prose.
   - `cx_applied` (`metadata["cx_applied"]`) -- the marker list showing which
     CX lane additions were actually applied to the delivered response
     (`preamble_stripped`, `partial_note`, `personal_account_note`,
     `contact_offer`, `international_directory_note`, `suggestions`); a
     regression here is a composition regression even if `outcome.kind`
     matches.
   - `answer_language` -- via `context_resolution`/`resolved_query`
     provenance in the capture record, or directly from
     `app.orchestrator.answer_language.resolve_answer_language` for CX
     cases; confirms Decision #6 (answer follows message language, widget
     selection eligibility unchanged) actually held live.
   - `failure_layer` (`final_answer.failure_layer`, only present with
     `--capture-final-answer`) -- distinguishes a dependency failure from an
     evidence gap from a guardrail refusal; R12 criterion 3 depends on this
     never being confused with `outcome.kind == evidence_missing`.
   - `retrieval_availability` / `search_channel_failures` -- R02 provider
     state from the question-stage retrieval; needed to tell a genuine
     dependency outage apart from a normal empty-evidence case (same
     distinction `failure_layer` makes at the answer layer, checked here at
     the retrieval layer).
   - `candidates_and_ranks` (`retrieval_rank_lists`) -- for the recall@5/@10/
     @30 and best-rank metrics in Stage 2's table.
   - `approved_evidence` (`response.citations`) -- for the citation-quality
     metric (does the cited section actually support the claim -- a human
     judgment against the source, not automatable from this field alone,
     but this field identifies which citation to check).
   - `call_counts` and `latency_seconds` -- for the cost-per-answer and
     latency p50/p95 metrics.
4. **Human review of every changed answer** (Stage 1 criterion 5): for each
   case where B0 and the candidate disagree on `outcome.kind`, `cx_applied`,
   or the answer text itself, a person reads both answers against the
   source and records a verdict -- this is not a step a script performs.

## Manifest built by this worker

- `docs/conversation-quality/phase3/manifests/r10_first_manifest_DRAFT.json`
  -- **75 cases** (up from the initial 43 after the 2026-09-19 multilingual
  rebalance, coordinator review of `62d51c2`): the original 30 R09 outline
  journeys plus 8 non-English duplicates of outline rows added for language
  coverage; the original 13 CX-specific additions (seven fallback states,
  one partial answer, one clarification, one contact escalation, one
  repair, one typo, one answer-language switch) expanded so that each of
  the seven fallback states now has 3 language variants (21 cases total),
  the answer-language switch covers 3 directions (fr-to-en widget,
  es-to-en widget, en-to-de widget), and repair/typo/contact-escalation
  each gained a non-English variant. The personal-account-question
  requirement is still satisfied by the `fallback_state_personal_account`
  cases, noted in their own `exposure` fields rather than duplicated.
  - `manifest_version: 1`, SHA-256
    `c8419690ff55894d0655df3b928b98f109038d217dcc7a4b23bca66df0af5bcb`
    (supersedes the prior draft's
    `4b9c56757053c0285725aac2fedcf810d2c401b57a7bfd8b6534c515f7082197`).
  - 61 development / 14 evaluation.
  - **Languages** (case count by `language`, all drawn from
    `services.market_config.get_supported_language_codes()` -- `da de en es
    fi fr it nl no ru sr`; `sv`/`pt` are NOT in this set, confirmed by
    import, despite being present in `CX_LANE4_LOCALIZATION.md`'s 12-locale
    route-copy table -- `ChatRequest.language` only accepts the market
    union, not the route-copy locale list; `sv` was therefore not usable no
    matter how the rebalance was done):

    | Language | Count |
    |---|---|
    | en | 41 |
    | de | 6 |
    | es | 5 |
    | fi | 5 |
    | fr | 5 |
    | nl | 3 |
    | ru | 3 |
    | da | 2 |
    | it | 2 |
    | no | 2 |
    | sr | 1 |

    Non-English: **34 / 75 = 45.3%**, spread across all 10 non-English
    languages `ChatRequest` accepts -- meets the coordinator's "~45%,
    spread across es, fr, de, fi, nl, it, no, da, ru, sr" target. Each of
    the seven fallback states has exactly 3 language variants (en + 2
    others, chosen to rotate through the full language list rather than
    repeating the same pair); the answer-language-switch case covers all
    3 requested directions; repair and typo each have one non-English
    variant (es and de respectively); international-sponsoring questions
    now run from three non-English sessions (`de`, `fi`, plus the existing
    `en`-language `CA`/`GB` sessions) in addition to the two English-session
    journeys from the original draft.
  - Countries: all 16 of `services.market_config.get_country_codes()` (`AT
    BE CA CH DE DK FI GB IT KG LU NL NO RS SE US`) were checked against;
    every case's `country` is one of these 16 (`US` 46, `CA` 8, `DE` 7,
    `FI` 3, `NL` 3, `DK` 2, `IT` 2, `NO` 2, `GB` 1, `RS` 1). Kenya, Ghana,
    Hong Kong, Tanzania, Uganda and Norway (as a discussed market) are
    referenced **by name inside message/turn text**, never as a `country`
    field value, since none of them is a valid `ChatRequest` country in
    this worktree's market configuration -- confirmed by importing
    `get_country_codes()` directly rather than assumed.
  - Roles: `new_prospect` and `active_distributor` used; all three
    `config.vera_persona.ROLE_CONTENT_SCOPES` values are valid,
    `compliance_officer` not exercised in this draft.
  - Loaded and validated with `capture_application_path.load_manifest`
    directly (not just eyeballed): zero `ManifestError`s, and a second pass
    confirmed every `country`/`language`/`role` against the real
    `market_config`/`vera_persona` modules (not preflight -- preflight never
    imports these; this second check was a separate, still-offline,
    read-only import done only to validate the draft, never to run
    anything through `AIOrchestrator`).
  - `git diff --check`: exit 0 (clean).
