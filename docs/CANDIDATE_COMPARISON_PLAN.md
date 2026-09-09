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

**"Current" is not `main`.** `main..HEAD` spans the whole unmerged branch -
publication, ingestion, the earlier numeric grounding work - and comparing
against it would attribute all of that to these five candidates. The baseline
is `c5391bb`, the frozen clarification candidate, which is the state
immediately before this work.

## The two arms

| | Path | Application code |
|---|---|---|
| Current | `../askvera-current` | `c5391bb` |
| Candidate | `askvera-deploy` | current tip |

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

## What this run cannot show

- **France's decimal rendering is not tested.** The notation reader is not
  connected to answer rendering, so `1,612CC` will be copied across exactly as
  it is today. This case tests the *condition*, not the number. Connecting the
  reader is a separate change and is deliberately not in this run.
- Five cases in one market group, English only, one session role.
- One run per arm shows a difference, not a rate. Two arms differing once is
  not evidence the difference is stable.
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
Approved ceiling for this work: **US$5**, which the first run is far inside.

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

Repeat or widen only if this first run is informative. If both arms answer
identically on all five, the candidates are not reaching these questions and
more repetitions will not change that.
