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
| Tip | `2ac8e92`, plus this document |
| `main` | unchanged |
| Working tree | pre-existing untracked files only, all left alone |
| Pre-existing unmerged branches | 12, untouched |

Baseline checks before any edit: **1267 passed, 1 skipped**, flake8 clean, shell
tests passing. No pre-existing failures. Every failure during the session was
introduced and resolved here.

## 2. Verification now

```
python -m pytest tests -p no:cacheprovider                 1443 passed, 9 skipped
python -m flake8 api app config services utils main.py     exit 0
bash tests/shell/test_deploy_log_pruning.sh                all checks passed
python scripts/run_benchmark.py --dry-run                  17 cases, valid
python scripts/run_retrieval_canary.py --validate-only     valid, 23 cases
```

**176 tests added.** `tests/` covers unit, governance, integration and shell;
the whole directory was run, not a subset.

**The 9 skips are not passes.** Eight are the PostgreSQL migration checks in
`tests/integration/test_review_migration_postgres.py`, which have never been
executed against any database - that remains a release blocker. The ninth is a
pre-existing AWS opt-in skip in `test_chat_flow.py`.

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
| 11 | `7dfdd1b` | Metadata conflict detection, no value ever guessed |
| 12 | `eb6dab1` | Publication gate: contradictions are not waivable |
| 13 | `36db48a` | Automatic activation forced through the same assessment |
| 14 | `852f3a2` | Review-storage migration and the document_version fix |
| 15 | `4b2b0a0` | A test database must be designated disposable twice |
| 16 | `9933920` | Recoverable publication; assessment stored with the status |
| 17 | `8da80ee` | Reviewer decision recorded; gate tested at the API boundary |
| 18 | `3df7f12` | The reviewer's screen: findings, pages, history, a reason |
| 19 | `2ac8e92` | Chunk-boundary grounding, including two recorded defects |

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
3. **Governing row** (`6bb6b18`, bounded in `52627fd`). The unit is the one
   beside the figure, or the nearest unit token before it, within 300
   characters and **not across a clause boundary**.

**This is a heuristic, not table-row understanding.** It has no notion of a row,
a column or a cell. Two limits are asserted in tests rather than left to be
found:

- Two currencies in one sentence with no delimiter between them: the nearer one
  governs and can be the wrong one, rejecting a correct claim. Conservative, but
  it costs a correct answer, and closing it needs structural parsing rather than
  a different window size.
- A bare figure with no unit in its clause has no attributable currency. The
  validator neither invents one nor rejects a claim it cannot confirm.

Tables continuing across pages and chunk boundaries are now tested
(`tests/unit/test_chunk_boundary_grounding.py`), and the tests found two
defects, both recorded as passing tests marked WRONG BEHAVIOUR:

- A currency stated once at the top of a long table does not survive chunking.
  The claim is grounded against the whole document and removed against its
  chunks. This deletes true figures. Widening the lookback does not fix it;
  carrying the governing heading onto the chunk at ingestion would.
- A full stop between a heading and its row makes the figure ungoverned, and an
  ungoverned figure accepts any unit the document mentions anywhere. So a DZD
  delivery charge can be stated in EUR because a membership table elsewhere is
  priced in EUR. This is the permissive half, and it lets a wrong answer out.

One reassurance did come out of it, previously unstated anywhere: the chunker's
450-character overlap exceeds the 300-character unit lookback, so a heading
close enough to govern a row is always in the same chunk as that row. Both
constants are now asserted, because tuning either breaks it silently.

Still untested against real layouts: whether 300 characters suits real records.

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
| 5. Ingestion and extraction | Advanced. Header-over-scan, metadata conflict detection, publication gate, recoverable publication, reviewer decisions, the reviewer's screen, table continuation and chunk boundaries. Two grounding defects found and recorded. |
| 6. Benchmark expansion | Blocked on corpus text for non-English documents. |
| 7. Automatic quality checks | Substantially covered by task 2. |
| 8. Resilience | Partially done. Timeout-versus-service-failure distinction, transient-versus-permanent retry, fallback carries no citations, fallback never cached. Injected-failure testing through the running pipeline and recovery timing remain undone. |

## 7. Known gaps and unverified claims

- **No live verification of anything here.**
- **The held-out set is empty.** Every case was authored or adjusted while
  fixing the system, so passing them measures whether known defects stay fixed.
  `held_out_cases` is reported so a run says this itself.
- **The office-hours assertion was changed after a failing run.** Both facts are
  in the record, but the change was prompted by behaviour and should be
  re-checked against the source by someone else.
- **The role case has never been run.** Its provenance says so.
- **Two recorded grounding defects**, both in §5: a distant currency heading is
  lost to chunking (deletes true figures), and a clause boundary makes a figure
  ungoverned, after which any unit the document mentions is accepted (lets a
  wrong answer out). Neither is fixed.
- **The PostgreSQL migrations have never been executed.** Eight skipped checks.
  Release blocker.
- **Append-only is enforced in the application only.** No code writes an UPDATE
  or DELETE against `ingestion_review_decisions`, and there is a test that keeps
  it that way. Whether the database role holds those grants is an
  infrastructure question nobody in this repository can answer, and revoking
  them has not been done.
- **The conditional publication claim is untested against PostgreSQL.** It is
  written as a single conditional UPDATE, which is the right shape; whether it
  actually serialises two live workers is a database property.
- **`reunion-delivery-cost` still fails** — the index does not fold accents.
- The unit vocabulary is a fixed currency list; an unlisted lowercase code
  yields no unit, which degrades to pre-existing behaviour.

## 8. Decisions and permissions needed

1. **Whether publication should require the generation pointer.** With
   `ADMIN_INGESTION_GENERATION_POINTER_ENABLED` off there is no commit point,
   so publication has no atomic step and no authority to confirm against. The
   code records that case as succeeded with detail saying visibility is
   unverified, which makes the gap visible without choosing. See
   `docs/RECOVERABLE_PUBLICATION_DESIGN.md`.

   The approval UI itself is now built: findings, affected page numbers,
   decision history and a required reason.
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
python -m pytest tests -p no:cacheprovider                 1443 passed, 9 skipped
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

---

# 12. Recoverable publication — 2026-09-08

| | |
|---|---|
| Tip | `2ac8e92` |
| `main` | unchanged, `bde45fb` |
| Tests | 1443 passed, 9 skipped |

**Established by reading the code, not assumed.** With
`ADMIN_INGESTION_GENERATION_POINTER_ENABLED` on, `_generation_filters` restricts
every retrieval to `ingestion_id`s drawn from the PostgreSQL table
`knowledge_active_generations`. The database pointer is the authority on what a
reader can reach; OpenSearch document status is not. So the pointer update is
the commit point, everything before it is invisible, and recovery reads the
pointer rather than reasoning about an exception. No second source of truth was
introduced. Full design in `docs/RECOVERABLE_PUBLICATION_DESIGN.md`; operator
notes in `docs/PUBLICATION_ROLLOUT_AND_RECOVERY.md`.

**What now exists.** Publication states with an idempotency key bound to the
revision. A claim that is one conditional UPDATE. Recovery that asks the
pointer what happened, so a worker killed after the commit point is not
republished and one killed before it is safely retried. The assessment written
in the same statement that marks a job ready for review. Reviewer decisions
persisted before the gate runs and separately from publication success. The
gate tested at the API boundary: a submitted approval of a self-contradicting
document returns 400. The reviewer's screen showing findings, affected page
numbers, decision history and requiring a written reason.

**What is not established.**

- Neither migration has run against PostgreSQL. Eight skipped checks. **Release
  blocker.**
- Whether the conditional claim serialises two live workers. A database
  property; the test asserts the statement's shape only.
- Two environment variables reduce accidental database targeting. They cannot
  prevent someone supplying the wrong values, and the refusal check only
  recognises the database this application is configured for.
- Two grounding defects found by the chunk-boundary tests, recorded and unfixed
  (§5).
- Nothing here has been exercised against the live pipeline or the real corpus.
