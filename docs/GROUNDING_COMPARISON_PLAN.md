# Bounded candidate comparison — plan

Prepared, not run. `--capture` refuses without
`--i-have-approval-for-paid-model-calls`, and there is a test that it refuses.

## What is being decided

Whether the stricter unit-attribution rule should ship. It has two directions
and they trade against each other:

- it removes figures whose unit nothing in the evidence supports — the benefit;
- it can remove figures that were correct, where the support exists but not in
  a form the rule recognises — the cost.

Seven contrast cases and nine corpus excerpts say the rule behaves as intended
on text somebody chose. That is a control, not coverage. This measures it on
the questions the benchmark actually asks, against the index as it stands.

## Arms

| | Index | Code | Approval needed |
|---|---|---|---|
| 1 | existing | `main` | paid model calls |
| 2 | existing | candidate | paid model calls |
| 3 | re-ingested with heading-carrying chunking | candidate | **also** approval to re-ingest documents |

Arms 1 and 2 differ only in code, so they are the comparison. Arm 3 is
separate on purpose: it changes stored data rather than behaviour, it needs
documents published through the ingestion path, and its result says nothing
about arms 1 and 2. Do not fold it in — the heading-carrying fix and the
attribution rule reach production by different routes and can be adopted
independently.

## Commands

```bash
git checkout main
python scripts/run_grounding_comparison.py --capture out/current.json --load-ssm \
    --i-have-approval-for-paid-model-calls

git checkout <candidate>
python scripts/run_grounding_comparison.py --capture out/candidate.json --load-ssm \
    --i-have-approval-for-paid-model-calls

# offline, no model calls, run from the candidate checkout
python scripts/run_grounding_comparison.py --compare out/current.json out/candidate.json
```

## Size and cost

17 benchmark cases × 3 repeats × 2 arms = **102 generation calls**, plus their
retrieval and planner calls. Repeats are needed because generation is
stochastic; a single run per case measures one sample of the model, not the
rule.

I do not have Bedrock rates, so I cannot give a figure. `run_benchmark.py`
already reports `measured_generation_cost_usd` when rates are supplied — pass
the same `--input-usd-per-million` / `--output-usd-per-million` there on one
run to get the per-case cost, then multiply by 102.

Start with `--limit 5 --repeat 1` to confirm the pipeline and the capture
format before spending the rest.

## Metrics

| Metric | What it means | Which direction is bad |
|---|---|---|
| `correct_facts_removed` | the arm removed a figure the evidence contains | the cost. A reader lost a fact. |
| `invented_facts_removed` | the arm removed a figure the evidence lacks | the benefit. The system working. |
| `accepted_but_unsupported_by_oracle` | the arm kept a figure the oracle judges unsupported | the leak the rule exists to close |
| `runs_missing_expected_text` | completeness | the answer stopped carrying a required fact |
| `runs_with_uncited_required_section` | citation correctness | the answer stopped citing the governing section |
| `abstentions` | the arm refused to answer | a rule that causes refusals is worse than one that trims figures |

**On the oracle.** There is no ground truth for "was this figure really
supported". One fixed rule is applied to both arms — the structural rule in the
checkout doing the evaluating. So
`accepted_but_unsupported_by_oracle` means "figures this arm kept that the
candidate rule rejects", which is a comparison against a stated standard and
not against truth. Read it that way or it flatters the candidate by
construction.

## What the result actually is

`changed_decisions` — every figure one arm kept and the other removed, with its
case. That list needs a person to open the section the figure came from and say
whether it was really supported. The totals are how you find the list.

Ship it if the adjudicated list shows the removals are figures whose unit the
evidence genuinely does not establish, and completeness and citations are
unchanged. Do not ship it if `correct_facts_removed` rises on figures a reader
would call correct — that is the failure mode that damages good answers, and
it is worse than the leak it closes.

## What this will not tell you

- Anything about markets the benchmark does not cover. Benelux and Nordic are
  68% of the corpus and have no cases.
- Anything about non-English answers beyond the cases that exist.
- Anything about arm 3. Re-ingestion is a separate exercise.
- Whether the *publication* changes work. Those are exercised by the
  PostgreSQL checks and the unit tests, not by this.
