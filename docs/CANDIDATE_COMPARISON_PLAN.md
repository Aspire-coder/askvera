# Current versus Candidate — final-answer comparison

Written 2026-09-08, before spending anything. Corrects an earlier proposal that
would not have measured what it claimed to.

## The correction

**`run_grounding_comparison.py` cannot do this run.** Its own docstring says
so: it freezes one set of pre-repair answers and scores that byte-identical set
with each arm's *numeric validator*. That isolates a validator change, which is
what it was built for. It cannot show anything about catalogue expansion, which
changes retrieval; about completeness, which changes restored text; or about
role-aware answers, which change what the repair path removes. Proposing it for
those was wrong.

What is needed is a full pipeline run per arm, and that is `run_benchmark.py`,
which runs the real pipeline and records the delivered answer.

**"Current" is not `main`, and is not production either.** `c5391bb` is the
**pre-change candidate baseline**: the frozen clarification candidate, the tip
immediately before this session's work. It is not what is deployed. `main` is
`bde45fb`, and the branch between `bde45fb` and `c5391bb` carries publication,
ingestion and the earlier numeric grounding work, none of which is measured
here.

So this run answers one question: *do these five candidates change delivered
answers, relative to the state just before them.* It says nothing about how the
branch as a whole compares with production. That is a separate comparison
against a separate baseline and has not been run.

## The two arms

| | Application revision |
|---|---|
| Current | `c5391bb7dbffdbba6e005ec871d824b2fa094a50` |
| Candidate | pinned at run time and recorded in the artifact - see below |

Neither arm is described as "the tip". Each run records its own
`summary.arm.revision` from `git rev-parse HEAD`, so the artifact names the
commit that produced it and a plan written today cannot mislabel a run made
tomorrow. The candidate revision at the time of writing is
`10d3b57` or later; the artifact is the authority, not this line.

`summary.arm` also records, for each arm: the generation model, the embedding
model, the index, whether the generation pointer is on, the state of the
country-name expansion flag, the glossary and query-planner flags, and the
semantic and embedding cache flags. Two arms are only comparable if these match
except where the change under test is, and a flag read from the environment
rather than from the code is exactly what silently differs between two
checkouts. The expansion flag reports `"absent"` in the Current arm rather than
`false`, so "the setting does not exist here" stays distinguishable from "the
setting is off".

Verified in the Current worktree: `country_names.py`, `number_notation.py`,
`qualifications.py`, `personal_claims.py` and `personal_history_validator.py`
are absent, and `OPENSEARCH_COUNTRY_NAME_EXPANSION_ENABLED` is not in its
settings. The arms differ in application code and nothing else.

**One harness, two applications.** A baseline running a different harness
measures the harness too, so the candidate's `scripts/run_benchmark.py` and
`tests/fixtures/benchmark_cases.json` were copied into the Current worktree.
Both arms report `fixture_sha256 74e734a7c492e933f5d510f5e69e12b7fb5ebee926964dd874bd760bfd6d71e6`.
`scripts/run_retrieval_canary.py`, which owns `run_pipeline_capture` and is what
actually drives a turn, is **identical** between `c5391bb` and the tip, so the
pipeline entry point is the same in both arms without copying anything.

## The five cases, and what each can show

Chosen with `--case`, not `--limit`: the top of the fixture is scope refusals,
which carry no figures for any of this to act on.

| Case | Candidate under test | What it can show |
|---|---|---|
| `reunion-delivery-cost` | A expansion | whether the accented spelling recovers a match that currently fails |
| `france-minimum-order` | C completeness | whether the 150EUR / 72-hour condition survives into the answer |
| `algeria-repeat-order-minimum` | C completeness | whether the first-order / after-first-purchase conditions survive |
| `algeria-existing-fbo-order-minimum-role` | C, D | whether the figure reaches the right category |
| `algeria-delivery-cost` | control | a case none of the candidates should change |

## Attribution: a different answer does not say why

Different passages can come from expansion or from model variation. Identical
passages can still produce different wording. Neither direction is readable
from the answers alone, so each run records the signals that separate them:

| Field | What it separates |
|---|---|
| `search_query_count` | whether expansion actually added queries on this turn |
| `sections`, `cited_sections` | whether different passages were reached, or the same ones worded differently |
| `answer_edit_flags` | which post-generation edit fired - `directory_order_size_restored` is candidate C acting |
| `personal_history_repair`, `removed_personal_claims` | candidate D acting, and on which sentence |
| `removed_numeric_claims`, `removed_but_present_in_source` | repair removing an invented figure against removing a real one |
| `global_documents_searched` | whether directory scope changed |

The added query **text** is not observable from the Current arm, which has no
expansion. It is derived offline instead: `country_name_queries(question)` is
deterministic and free, so the queries the candidate adds for each of the five
questions can be printed locally and compared against the count difference.
That is a derivation, not an observation, and should be labelled as one.

**A count that did not change means expansion did not fire on that turn**,
which is a finding about the candidate rather than about the question.

## What this run cannot show

- **France's decimal rendering is not tested.** The notation reader is not
  connected to answer rendering, so `1,612CC` will be copied across exactly as
  it is today. This case tests the *condition*, not the number. Connecting the
  reader is a separate change and is deliberately not in this run.
- Five cases in one market group, English only, one session role.
- One run per arm shows a difference, not a rate. Two arms differing once is
  not evidence the difference is stable, and generation varies between runs of
  identical code.
- **Latency is not comparable from this run.** Five different questions, once
  each, mixes cold and warm: the first turn of a process pays for imports,
  configuration loads and empty caches, and the five questions differ in
  retrieval work anyway. `duration_ms` is recorded per run and the first turn
  of each arm should be read as a cold measurement and excluded from any
  comparison. A latency comparison needs the same question repeated, which this
  run does not do.
- The scoring rule is a stated standard, not ground truth. Every changed answer
  needs a person to open the section and adjudicate it.

## Cost

**Corrected.** An earlier note said the pilot was 19 turns; it was **six**, at
approximately **$0.07 estimated Haiku usage**. That is about **$0.0117 per
turn** if usage is comparable.

| Run | Executions | Haiku, extrapolated |
|---|---:|---|
| First comparison, 1 per arm | 10 | **~$0.12** |
| If later repeated 3x per arm | 30 | ~$0.35 |

Embeddings (`amazon.titan-embed-text-v2:0`) and other AWS usage are additional
and not in these figures. Per-turn cost varies with retries, planning and
repair, so this is an extrapolation from one six-turn run, not a quote.

**An estimate is not an authorization.** This document does not record one. The
earlier six-turn authorization was scoped to that pilot and does not carry
here. Whoever runs the commands below is spending against their own approval
for this run, and a figure being small is not a reason to skip asking.

## Commands

Run on the deployment host, one arm at a time.

```
# Current
cd ../askvera-current
python scripts/run_benchmark.py --load-ssm --repeat 1 \
  --artifact out/current.json \
  --case reunion-delivery-cost \
  --case france-minimum-order \
  --case algeria-repeat-order-minimum \
  --case algeria-existing-fbo-order-minimum-role \
  --case algeria-delivery-cost

# Candidate
cd ../askvera-deploy
python scripts/run_benchmark.py --load-ssm --repeat 1 \
  --artifact out/candidate.json \
  --case reunion-delivery-cost \
  --case france-minimum-order \
  --case algeria-repeat-order-minimum \
  --case algeria-existing-fbo-order-minimum-role \
  --case algeria-delivery-cost
```

Validate the selection first, free and with no model calls, by adding
`--dry-run`. Both arms should report 5 cases, 5 runs, 5 generation calls and
the same fixture hash.

## What to inspect afterwards

The artifact holds, per run: the delivered `answer`, the retrieved `sections`
and `cited_sections`, `citations`, `abstained`, `clarified`, `removed_numeric_claims`,
`removed_but_present_in_source`, `duration_ms` and the generation token counts. The four things worth reading
first, in this order:

1. **Final answers, side by side.** Did the France answer gain its condition?
   Did Réunion return anything at all?
2. **Supporting passages.** A changed answer from a changed section is
   expansion working; a changed answer from the same section is not.
3. **Refusals.** A candidate that refuses where Current answered has cost the
   reader something, and needs the section opened to say whether it was right.
4. **Latency.** Expansion adds up to four queries, each a text and a vector
   search. Compare warm turns; the first turn of a process pays for cold
   caches and configuration loads.

Review all ten final answers against their sources, including the control that
should not change - a control that moved is as informative as a case that did.

Treat any improvement as preliminary until repeated. One run per arm can show a
difference; it cannot show that the difference is stable, because generation
varies between runs of identical code.

**Identical answers do not mean the candidates were inactive.** Check whether
the code path ran before deciding anything: `search_query_count` says whether
expansion added queries, `answer_edit_flags` says whether restoration fired,
`personal_history_repair` says whether removal did. A candidate that ran and
changed nothing, a candidate that never ran, and a candidate that ran and was
undone downstream are three different findings needing three different next
steps - and repetition is worth considering in the first and third, not the
second.
