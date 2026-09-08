# Retrieval improvement session — current status

Date: 2026-09-08. Rewritten after two review rounds; this is the single current
statement, superseding the earlier layered version.

**Nothing was merged, pushed or deployed. No AWS resource, index, credential or
live configuration was touched. No paid model call was made. No scheduled task
was created or restarted.**

## 1. State

| | |
|---|---|
| Baseline | `bde45fb` on `main` |
| Tip | `d365209`, plus this document |
| `main` | unchanged |
| Working tree | pre-existing untracked files only, all left alone |
| Pre-existing unmerged branches | 12, untouched |

Baseline checks before any edit: **1267 passed, 1 skipped**, flake8 clean, shell
tests passing. No pre-existing failures. Every failure during the session was
introduced and resolved here.

## 2. Verification now

```
python -m pytest tests -p no:cacheprovider                 1341 passed, 1 skipped
python -m flake8 api app config services utils main.py     exit 0
bash tests/shell/test_deploy_log_pruning.sh                all checks passed
python scripts/run_benchmark.py --dry-run                  17 cases, valid
python scripts/run_retrieval_canary.py --validate-only     valid, 23 cases
```

**74 tests added.** `tests/` covers unit, governance, integration and shell; the
whole directory was run, not a subset.

**What this does not establish.** No change here has been exercised against the
live pipeline or the real corpus. Unit-test success is not measured retrieval
accuracy, and none of these numbers says anything about delivered answers.

## 3. The commits, in dependency order

The branches are stacked; each was cut from the previous. Merging the tip takes
all of them.

| # | Commit | What it does |
|---|---|---|
| 1 | `80b99a3` | Generated negative controls; first unit binding |
| 2 | `e8bbe80` | Refusal classification from reviewed copy only |
| 3 | `b2d8ba2` | Per-turn conversation assertions |
| 4 | `245047c` | Preflight reports a heading over an unreadable body |
| 5 | `168db8e` | Unit must exist in the source, not only beside the figure |
| 6 | `6a9c483` | Every case labelled development; held-out set is empty |
| 7 | `8660acb` | Low-text image pages logged at ingestion |
| 8 | `2a00a90` | Two over-claimed statements corrected (docs) |
| 9 | `6bb6b18` | Unit bound to the governing row, not the document |
| 10 | `d365209` | Role case and per-turn language switching |

**Rollback order is the reverse of this list, with tests run after each step.**
These commits touch overlapping code — 1, 5 and 9 are successive layers of the
same mechanism — so reverting out of order will not apply cleanly.

## 4. What changed at runtime

Four runtime files. Three are purely additive:

| File | Removed lines | Nature |
|---|---:|---|
| `app/evidence.py` | 0 | new function |
| `services/document_preflight.py` | 0 | new field |
| `services/knowledge_ingestion.py` | 0 | new logging |
| `app/validation/validators/numeric_grounding_validator.py` | 3 | answer behaviour |

**Correction from an earlier version of this document:** zero removed lines is
not zero risk. Added code still changes execution paths, serialisation, logging
volume, performance and error behaviour. The numeric grounding change is the
principal risk to delivered answers; it is not the only conceivable runtime
risk, and the earlier claim that it was is withdrawn.

## 5. Unit binding — three layers, and what is actually established

This is the one mechanism that changes answers, and it took three attempts.

1. **Adjacency** (`80b99a3`). A claim's unit must match the unit beside the
   matched figure. Caught `900 EUR` against `900 DZD`.
2. **Document-wide presence** (`168db8e`). A claim's unit must appear somewhere
   in the source. Caught a bare source figure with an invented currency, a
   heading-scoped unit, and an unlisted code.
3. **Governing row** (`6bb6b18`). The unit is the one beside the figure, or the
   nearest unit token before it, bounded at 300 characters.

Layer 3 exists because review supplied a counterexample layer 2 accepted:

```
Delivery charges - DZD
Standard delivery: 900
Membership charges - EUR
Annual membership: 20
```

Both currencies appear, so "Standard delivery costs 900 EUR" satisfied a
document-wide check while naming the wrong currency for that row. All four
directions now behave correctly.

**Established:** the rule behaves correctly on synthetic records covering
adjacency, inheritance, override, bounded lookback, unlisted codes and bare
figures.

**Not established:** how often mixed-unit blocks occur in the real corpus;
whether inheritance crosses a page break; whether the 300-character bound is
right for real layouts; and any effect on real answers. All need corpus text or
a live run.

## 6. Task status

| Task | Status |
|---|---|
| 1. Evaluation foundation | Advanced. Per-turn assertions, per-turn language, refusal classification without model calls, development/held-out separation. |
| 2. Numeric and formatting discovery | Advanced. 34 generated mutation controls; three-layer unit binding. |
| 3. Grounding and completeness | Partially advanced. Unit binding closes one class. Short-claim, heading and negation bypasses in the evidence contract remain open and pinned by a test; the contract is dormant (`EVIDENCE_GATED_OUTPUT_ENABLED` false). |
| 4. Scope and conversation | Partially done. Per-turn machinery, one multi-market chain, one role case, language switching. |
| 5. Ingestion and extraction | Partially done. Header-over-scan detected and logged. Table continuation, metadata conflicts, chunk boundaries not started. |
| 6. Benchmark expansion | Blocked on corpus text for non-English documents. |
| 7. Automatic quality checks | Substantially covered by task 2. |
| 8. Resilience | **Not started.** Timeout, dependency-failure and retry tests are feasible locally and were not reached. |

## 7. Known gaps and unverified claims

- **No live verification of anything here.**
- **The held-out set is empty.** Every case was authored or adjusted while
  fixing the system, so passing them measures whether known defects stay fixed.
  `held_out_cases` is reported so a run says this itself.
- **The office-hours assertion was changed after a failing run.** Both facts are
  in the record, but the change was prompted by behaviour and should be
  re-checked against the source by someone else.
- **The role case has never been run.** Its provenance says so.
- **Extraction warnings reach logs, not the approving reviewer.** See §8.
- **`reunion-delivery-cost` still fails** — the index does not fold accents.
- The unit vocabulary is a fixed currency list; an unlisted lowercase code
  yields no unit, which degrades to pre-existing behaviour.

## 8. Decisions and permissions needed

1. **Approval-UI surfacing of extraction warnings.** Logging is operational
   visibility, not informing the person approving an upload. A page-level
   warning in the approval workflow, with an explicit review-or-recover
   decision, is outstanding — and *when* an unresolved page should block
   publication is a policy decision I have deliberately not defaulted.
2. **Accent folding.** Inspect the active analyser, measure a candidate index
   against the current one on the same questions with and without diacritics,
   and decide per language whether folding merges words that should stay
   distinct. Do not change the active index first.
3. **Reviewed refusal copy for seven locales** — it, da, fi, no, sr, sv, ru have
   no reviewed `insufficient_evidence` wording and currently receive an
   unreviewed live translation. Whether that is acceptable for approved policy
   communication is a governance decision, not a technical one.
4. **Corpus text** for non-English benchmark cases.
5. **A bounded, separately authorised live comparison** — the only thing that
   would turn any of this into evidence about delivered answers.
6. **Bedrock rates**, if a cost figure is wanted.

## 9. Before merging

```
git checkout <tip>
python -m pytest tests -p no:cacheprovider
python -m flake8 api app config services utils main.py
bash tests/shell/test_deploy_log_pruning.sh
python scripts/run_benchmark.py --dry-run
python scripts/run_retrieval_canary.py --validate-only
```

All five pass on the tip. Branches passing individually is not evidence the
combination passes; these were run on the combined stack.

**Run the candidate in the approved test environment BEFORE production
deployment**, not after. The blocking canary is the first real check —
`belgium-office-hours-survive-repair` and `algeria-minimum-order-delivered` both
exercise grounding and would be the first to show a unit-binding regression —
followed by a benchmark run. Post-deployment verification is a separate step
after that, not a substitute for it.

**No improvement is established yet; investigate any movement in either
direction.** An earlier version of this document said "expected movement: none",
which was wrong in kind: a general validator change can affect cases well beyond
the reproduction it was written for, and a score that improves needs explaining
just as much as one that drops.

## 10. Confirmation

Nothing merged. Nothing pushed. Nothing deployed. No index, AWS resource,
credential or live configuration modified. No paid model call. No branch,
worktree, source document or uncommitted user change deleted or overwritten.


---

# 11. Candidate freeze — 2026-09-08

Recorded so the reviewed thing and the tested thing are the same thing.

| | |
|---|---|
| Baseline | `bde45fb` on `main` |
| Candidate tip | `d8bb18dc6f48a777aa2dee76a2aeefd6d6366484` |
| Branch | `chore/freeze-candidate-and-correct-handoff`, tip of a 14-commit stack |
| `main` | unchanged, `bde45fb` |

**Configuration:** none changed. No settings default, SSM parameter, feature
flag or deployment file was edited. `EVIDENCE_GATED_OUTPUT_ENABLED` remains
false, `ADMIN_TEXTRACT_OCR_ENABLED` untouched, alarm notification settings
untouched.

**Test results at the freeze:**

```
python -m pytest tests -p no:cacheprovider                 1341 passed, 1 skipped
python -m flake8 api app config services utils main.py     exit 0
bash tests/shell/test_deploy_log_pruning.sh                all checks passed
python scripts/run_benchmark.py --dry-run                  17 cases, valid
python scripts/run_retrieval_canary.py --validate-only     valid, 23 cases
```

**Preserved and untouched:** 12 pre-existing unmerged branches, all untracked
working-tree files including `docs/audits/**` and `scratch/`, and every
uncommitted user change.

Work continuing after this freeze is additive and recorded in the sections
below; the freeze point is the commit named above.
