# Retrieval improvement session — handoff

Date: 2026-09-08
**Nothing was merged, pushed or deployed. No AWS resource, index, credential or
live configuration was touched. No paid model call was made.**

## 1. Repository state

| | |
|---|---|
| Starting commit | `bde45fb` on `main` |
| Ending commit | see §13 — stack extended after review |
| `main` | unchanged, still `bde45fb` |
| Working tree | pre-existing untracked files only (`.claude/`, `docs/audits/**`, `scratch/`, four untracked `docs/*.md`), all left untouched |
| Pre-existing unmerged branches | 12, none touched |

### Baseline before any edit

```
python -m pytest tests            1267 passed, 1 skipped
python -m flake8 <CI paths>       exit 0
bash tests/shell/test_deploy_log_pruning.sh   all checks passed
```

No pre-existing failures. Every failure seen during the session was introduced
and then resolved by the work below.

## 2. Task classification

| Task | Status | Note |
|---|---|---|
| 1. Evaluation foundation | **Partially implemented → advanced** | Same-execution capture, cache bypass, section-ID scoring, unscored handling and repair-kind separation were already done earlier today. Per-turn assertions and multilingual refusal classification were the real gaps; both now implemented. Regression/held-out separation **not done** — see §7. |
| 2. Numeric and formatting discovery | **Advanced** | Generated negative controls added; a real unit-binding defect found and fixed. |
| 3. Grounding, citations, completeness | **Partially advanced** | Unit binding closes one class. Short-claim, heading and negation bypasses in the evidence contract remain open and are already pinned by a test; the contract is dormant in production (`EVIDENCE_GATED_OUTPUT_ENABLED` false). Not changed — see §10. |
| 4. Scope and conversation tests | **Partially implemented** | Per-turn machinery plus one multi-market chain case. Role distinctions and language switches not covered. |
| 5. Ingestion and extraction | **Advanced** | Header-over-scan case implemented. Table continuation, metadata conflicts and chunk-boundary work not started. |
| 6. Representative benchmark expansion | **Blocked** | Requires corpus text for non-English documents. See §10. |
| 7. Automatic quality checks | **Substantially covered by task 2** | 34 generated mutation controls prove the notation suite fails on wrong values. Wrong-country and wrong-source detection already covered by existing tests. |
| 8. Resilience and operational gaps | **Not started** | Deprioritised in favour of the correctness work above. |

## 3. Changes, in merge order

The four branches are **stacked** — each was cut from the previous one. Merge in
this order, or merge the tip alone to get all four.

### 3.1 `test/notation-negative-controls` — commit `80b99a3`

**Problem.** The generated notation suite only asserted that a value written
differently is still recognised. Positive-only generation is a machine for
teaching a validator to accept everything: every case passes if grounding
always says yes.

**Fix.** `_mutations()` generates, for each figure in the real records, a
changed last digit, an order-of-magnitude slip and a moved decimal separator —
34 rejection controls against 31 equivalences. A mutation landing on another
real figure in the same record is skipped rather than asserted.

**What it exposed, and the second fix.** `900 EUR` was accepted against a record
stating `Delivery Cost: 900 DZD`, and `0,200 DZD` against `0,200CC`. The number
matched, the subject matched, and nothing compared the unit. A claim carrying a
unit is now supported only by a source occurrence whose unit agrees; an
occurrence with no unit still counts, because many corpus figures are bare.

Two earlier attempts at the unit vocabulary were wrong and are recorded in the
commit: matching any short token treated the "and" in "48 and 96 hours" as a
unit; requiring capitals worked on the answer and never on the source, because
`_normalize` casefolds source text.

Files: `app/validation/validators/numeric_grounding_validator.py`,
`tests/unit/test_numeric_notation_coverage.py`.

### 3.2 `test/multilingual-refusal-classification` — commit `e8bbe80`

**Problem.** The benchmark built refusal markers through
`localized_conversation_response`, which performs a **live model translation**
when a locale lacks reviewed copy. Detecting whether an answer was a refusal
could therefore spend a model call and produce a marker that differs between
requests.

**Finding.** Seven of twelve configured locales — it, da, fi, no, sr, sv, ru —
have no reviewed `insufficient_evidence` copy, the commonest refusal in the
corpus, and those markets hold most of it.

**Fix.** `configured_conversation_response()` returns reviewed copy only and
reports whether it is reviewed for the requested locale. Markers are built from
it; a test fails if a translation is attempted. The summary now lists
`languages_with_unreviewed_refusal_copy`.

Production behaviour is unchanged: readers still get a translation, which is
right.

Files: `app/evidence.py`, `scripts/run_benchmark.py`,
`tests/unit/test_benchmark_harness.py`.

### 3.3 `feat/benchmark-per-turn-assertions` — commit `b2d8ba2`

**Problem.** A conversation case asserted only its final answer. The last
question in a chain is usually a follow-up whose subject was established
earlier, so a case could pass while turn one answered the wrong market. Scope
and market carry-forward fail in the middle of a chain.

**Fix.** `run_pipeline_capture` returns every prior turn's response in a
defaulted field, so the canary, its ten test stubs and the tuple entry point are
untouched. A conversation entry may now carry its own expectations and is scored
for refusal-versus-answer, required and forbidden facts, and cited sections with
country qualification. Bare-string turns replay unscored, as before. Failures
are prefixed with the turn number.

One case added: Belgium → Germany → "and what is the minimum order size there?",
each turn required to cite its own market's section. **Figures are deliberately
not asserted** — the Belgium and Germany record text has not been dumped, and
asserting an unread value would be inventing it.

Files: `scripts/run_retrieval_canary.py`, `scripts/run_benchmark.py`,
`tests/fixtures/benchmark_cases.json`, `tests/unit/test_benchmark_harness.py`.

### 3.4 `feat/preflight-flags-low-text-image-pages` — commit `245047c`

**Problem.** A page was inspected for images only when it had almost no text. A
printed section title above a scanned fee table clears the 40-character bar, so
the page counted as fully extracted and nothing recorded that the body was never
read.

**Fix.** Pages with text under 250 characters that also carry an image are
reported in `low_text_image_page_numbers`. It **reports and decides nothing** —
`requires_ocr` is unchanged, because policy pages carry letterheads and forcing
OCR on all of them would hold documents that are fine. Two controls pin that.

Files: `services/document_preflight.py`, `tests/unit/test_document_preflight.py`.

## 4. Tests run, and results

Run on the stack tip (`245047c`):

```
python -m pytest tests -p no:cacheprovider     1320 passed, 1 skipped
python -m flake8 api app config services utils main.py    exit 0
bash tests/shell/test_deploy_log_pruning.sh    all checks passed
python scripts/run_benchmark.py --dry-run      16 cases, 48 runs, 54 generation calls
python scripts/run_retrieval_canary.py --validate-only    valid, 23 cases
```

Baseline was 1267 passed / 1 skipped, so **53 tests were added**. The single
skip is pre-existing.

`tests/` covers `unit`, `governance`, `integration` and `shell`. The whole
directory was run, not a subset — earlier today a subset run hid five failures
and blocked a deploy.

**Not run:** any live benchmark, any model call, any deployment, any index
operation. No paid run was made, and no prior spending approval was assumed.

## 5. Known failures and unverified claims

- **No live verification of any change here.** Everything is unit-level. The
  unit-binding change in particular alters production grounding behaviour and
  has not been exercised against the real corpus.
- **`reunion-delivery-cost` still fails** in the benchmark, from before this
  session. Cause established: the index does not fold accents (`Reunion` matches
  0 sections, `Réunion` matches 6). Not addressed — see §10.
- **The unit vocabulary is a fixed list of currency codes.** A code not on it
  yields "no unit", which degrades to the pre-existing behaviour rather than to
  a false rejection, but it does mean the check silently does nothing for an
  unlisted currency.
- **`_score_prior_turns` is tested against stub responses only.** No multi-turn
  case has been run through the live pipeline with per-turn assertions.

## 6. Coverage added

| Area | Added |
|---|---|
| Numeric notation | 34 generated rejection controls, 7 unit-binding cases |
| Multilingual | Refusal-copy completeness pinned for all 12 locales; no-model-call guarantee |
| Conversation | Per-turn scoring, 4 tests, 1 three-turn benchmark case |
| Ingestion | Header-over-scan case plus 2 controls |

## 7. Gaps remaining

- **Regression versus held-out separation** (task 1). The fixture does not mark
  which cases were used to tune fixes. Three of the sixteen have had assertions
  corrected against observed behaviour, so the set is partly development data
  and should not be quoted as held-out evidence.
- **Non-English answerable cases** (task 6) — blocked, §10.
- Role distinctions, language switches, table continuation, metadata conflicts,
  chunk boundaries, resilience and operational checks (tasks 4, 5, 8).

## 8. Configuration, migration and re-ingestion requirements

None for these four branches. They add tests and two behaviour changes that need
no migration.

Separately outstanding from earlier work, unchanged by this session: the accent
folding reindex (§10), and the 15 documents with no effective date.

## 9. Risks and rollback

| Change | Risk | Rollback |
|---|---|---|
| Unit binding | A correct answer using a currency the corpus writes differently could be rejected. Mitigated: an unlisted code disables the check rather than rejecting. | Revert `80b99a3` |
| Per-turn assertions | None to production — benchmark and canary tooling only. The canary field is defaulted. | Revert `b2d8ba2` |
| Refusal markers | None to production. | Revert `e8bbe80` |
| Preflight reporting | None — reports a new field, changes no decision. | Revert `245047c` |

The only change reaching delivered answers is **unit binding**. If it misbehaves
in the canary, revert `80b99a3` alone; the other three are independent of it in
effect, though stacked in git.

## 10. Decisions and permissions needed

1. **Accent folding.** The index does not fold accents, so unaccented queries
   miss accented text across 15 non-English documents. Fix is an asciifolding
   analyzer plus a reindex of 17,896 sections. The index mapping is not in this
   repository. **Your call.**
2. **Reviewed refusal copy for seven locales.** `insufficient_evidence` is
   missing for it, da, fi, no, sr, sv, ru. Needs the same wording review the
   English copy had. I did not write it — inventing approved copy is out of
   bounds.
3. **Corpus text for non-English benchmark cases.** Blocked without a dump:
   `scripts/dump_corpus_sections.py --load-ssm --document-type policy --language <x>`.
   Authoring cases without reading the source would produce a benchmark that
   measures the assumption.
4. **Whether to enable the evidence contract.** Still dormant. Its short-claim
   gap is pinned by a test and deliberately unfixed, because closing it needs a
   false-rejection measurement that does not exist.
5. **Bedrock rates**, if a cost figure is wanted from the benchmark.

## 11. Recommended pre-merge regression checks

Branches passing individually does not mean the combination passes. Before
merging:

```
git checkout feat/preflight-flags-low-text-image-pages
python -m pytest tests -p no:cacheprovider
python -m flake8 api app config services utils main.py
bash tests/shell/test_deploy_log_pruning.sh
python scripts/run_benchmark.py --dry-run
python scripts/run_retrieval_canary.py --validate-only
```

All five were run on the tip and pass. After deploying, the checks that matter
are the **blocking canary** — 23 cases, including `belgium-office-hours-survive-repair`
and `algeria-minimum-order-delivered`, both of which exercise grounding and would
be the first to show a unit-binding regression — and then a benchmark run.

Expected benchmark movement: **no change to the score**. These branches add
coverage and fix a defect no current case exercises. If the score moves, find
out why before accepting it.

## 12. Confirmation

Nothing was merged. Nothing was pushed. Nothing was deployed. No index, AWS
resource, credential or live configuration was modified. No scheduled task was
created or restarted. No paid model call was made. No existing branch, worktree,
source document or uncommitted user change was deleted or overwritten.


---

# 13. Second round — changes made after your review

Your review was acted on rather than filed. Five more commits, same stack,
still nothing merged, pushed or deployed.

| Commit | Branch | Your point |
|---|---|---|
| `168db8e` | `test/unit-binding-contrast-cases` | 1. Unit binding still permissive |
| `6a9c483` | `feat/separate-development-from-heldout` | 3. Evaluation set not cleanly held out |
| `8660acb` | `feat/surface-low-text-image-pages-at-ingestion` | 2. Detected is not recovered |
| `f1b0a0f` | `docs/correct-accent-and-translation-claims` | 4. Accent fix needs an experiment, not a reindex |

## 13.1 Unit binding was permissive — confirmed and closed

You were right. Probing the cases you named found three genuine holes: a bare
source figure beside an answer that invents a currency, a unit stated once in a
table header rather than beside each figure, and a code no vocabulary lists.

One rule closes all three: **a claim's unit must appear somewhere in the source
document**, not merely beside the matched figure. That handles the header case
adjacency cannot. An unlisted three-letter code now counts as a unit when the
answer capitalises it — case survives on the answer side and not on the source
side, which is casefolded.

Two of my five original probes were badly built, and the conclusions should not
be over-read: the "wrong fee sharing a number" source genuinely did support the
claim, and the ambiguous-dollar probe paired New Zealand content with Algeria's
title, so it failed on market matching rather than currency. Rebuilt, all seven
behave correctly.

**Still not proven:** units inherited across a page break, and a unit present in
the source for a different figure entirely. Both need corpus text.

## 13.2 The evaluation set — stronger than the handoff first admitted

Not three adjusted cases among sixteen clean ones. **Every case was authored or
adjusted while fixing the system on 2026-09-08. The held-out set is empty.**

Cases now carry a required `evaluation_set`, the summary reports the two apart
rather than averaging, and `held_out_cases` is reported explicitly so a run that
establishes nothing about generalisation says so in its own output.

Your related point is not solved by a label and remains open: a corrected
expectation must come from the source, not from what the bot did. The
office-hours case is the one to re-check — both facts are in the record, but the
change was prompted by a failing run.

## 13.3 Detected is not recovered — closed at the reporting level

`low_text_image_page_numbers` was computed and read by no caller. Ingestion now
logs the pages and filename where they exist. It still does not block, and
**when an unresolved page should block publication is the decision I am leaving
to you** rather than defaulting.

## 13.4 Two claims corrected

The accent section recommended reindexing outright; it now says inspect the
analyser, measure a candidate index, and decide per language whether folding
merges words that should stay distinct.

And I had written that live translation of refusal copy "is right". The premise
holds, the conclusion does not follow, and it is recorded as an open governance
gap rather than a settled design choice.

## 13.5 Runtime-changing diff, isolated as requested

Across the whole stack, four runtime files change:

| File | Removed lines | Nature |
|---|---:|---|
| `app/evidence.py` | 0 | new function only |
| `services/document_preflight.py` | 0 | new field only |
| `services/knowledge_ingestion.py` | 0 | new logging only |
| `app/validation/validators/numeric_grounding_validator.py` | 3 | **the only behaviour change** |

**One mechanism carries all the runtime risk: unit binding.** If the canary
shows a grounding regression, revert `80b99a3` and `168db8e`; everything else is
additive.

## 13.6 Verification after round two

```
python -m pytest tests -p no:cacheprovider     1333 passed, 1 skipped
python -m flake8 api app config services utils main.py    exit 0
python scripts/run_benchmark.py --dry-run      16 cases, 48 runs, 54 generation calls
python scripts/run_retrieval_canary.py --validate-only    valid, 23 cases
```

Baseline was 1267. **66 tests added**, no pre-existing failure disturbed.

## 13.7 Still not done from your list

- **Role and language-switch tests.** Feasible in principle; a role case needs
  the Algeria record's FBO-versus-Preferred-Customer distinction expressed as a
  benchmark case, which cannot be validated without a live run.
- **Failure-recovery and resilience tests.** Not started.
- **Table continuation, metadata conflicts, chunk boundaries.** Not started.
- **A bounded live comparison.** Needs your authorisation and is the only thing
  that would turn any of this into evidence about delivered answers.
