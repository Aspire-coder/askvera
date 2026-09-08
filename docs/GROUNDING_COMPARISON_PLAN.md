# Bounded candidate comparison — plan

Prepared and dry-run. No paid run has happened. `--freeze` refuses without both
an approval flag and an explicit `--max-turns`, and there are tests for both
refusals.

## What is being decided

Whether the stricter unit-attribution rule should ship. It moves figures in
both directions:

- it removes figures whose unit nothing in the evidence supports;
- it can remove figures that were correct, where the support exists but not in
  a form the rule recognises.

**Neither direction is universally worse than the other.** Losing a fact a
distributor asked for and stating a charge in the wrong currency are different
harms, and which matters more depends on the question, the market and who is
reading. They are measured separately and reported separately, and the decision
is a judgement, not an arithmetic comparison of two counts.

Seven contrast cases and nine corpus excerpts say the rule behaves as intended
on text somebody chose. That is a control, not coverage.

## Two exercises, in order

**A. Repair-only comparison.** Freeze one set of pre-repair answers and their
evidence, then score that identical set with each arm's validator. Every
difference is the validator, because the input is byte-identical. One paid
freeze, then free.

**B. End-to-end evaluation.** Run the full pipeline per arm. Answers differ for
reasons unrelated to grounding, so this measures the system rather than the
rule.

Do A first. Conflating the two is how generation variance gets reported as a
validator effect.

## Arms

| | Evidence | Code | Approval |
|---|---|---|---|
| 1 | frozen set | `main`, via a worktree | — (free) |
| 2 | frozen set | candidate | — (free) |
| 3 | re-ingested with heading-carrying chunking | candidate | re-ingestion approval, separately |

**One harness, two worktrees.** `run_grounding_comparison.py` does not exist on
`main`, so "check out main and run it" cannot work. Scoring instead loads the
application code from `--app-root` and reports the file it actually loaded, so
an arm that silently scored itself is visible. `--compare` refuses if both arms
loaded the same file, or if they scored different frozen sets.

Arm 3 stays separate: it changes stored data rather than behaviour, and the
heading-carrying fix and the attribution rule can be adopted independently.

## Commands

```bash
git worktree add ../askvera-main main

python scripts/run_grounding_comparison.py --preflight

python scripts/run_grounding_comparison.py --freeze out/frozen.json --load-ssm \
    --i-have-approval-for-paid-model-calls --max-turns 6

python scripts/run_grounding_comparison.py --score out/frozen.json \
    --app-root ../askvera-main --out out/main.json
python scripts/run_grounding_comparison.py --score out/frozen.json \
    --app-root . --out out/candidate.json
python scripts/run_grounding_comparison.py --compare out/main.json out/candidate.json
```

## Size, and why the first estimate was wrong

The fixture is **17 cases but 19 turns**: `belgium-then-germany-market-continuity`
replays two prior turns and then asks its own question, so it costs three
executions. An earlier estimate counted cases and called them calls.

Freezing is one arm, not two — that is the point of the repair-only design:

| | turns | × repeat 3 | 
|---|---:|---:|
| freeze (one arm) | 19 | **57 turn executions** |
| end-to-end, later, two arms | 19 | 114 turn executions |

**A turn is not one paid call.** Routing, planning, evidence selection,
generation, retries and repair may each call a model. Treat 57 as a lower
bound on calls, not an estimate of them.

I do not have Bedrock rates and cannot give a figure. Measure it instead:

1. `--preflight` — free, confirms the counts.
2. `--freeze --max-turns 6 --repeat 1` — a handful of turns. Read the real
   cost from CloudWatch or the Bedrock console before continuing.
3. Multiply, decide, then run the rest with `--max-turns` set to that decision.

A checkpoint is written after every turn, so an interrupted run keeps what it
paid for and the bound is real rather than nominal.

## Metrics

Every count is mechanical. None of them labels a figure correct or invented.

| Metric | What it counts |
|---|---|
| `figures_removed` | figures this arm's rule removed |
| `removed_and_present_in_evidence` | of those, the ones whose string occurs in a retrieved section |
| `removed_and_absent_from_evidence` | of those, the ones that do not occur at all |
| `runs_missing_required_text` | the answer lost a fact the case requires |
| `runs_with_forbidden_text` | the answer contains something the case forbids |
| `runs_with_uncited_required_section` | the governing section was not cited, where the case requires citation |
| `abstentions` | the arm refused to answer |

**"Present in evidence" is not "was correct".** The dry run makes this
concrete: for the answer *"Standard delivery costs 900 EUR"* against a source
reading `Delivery charges - DZD / Standard delivery: 900`, the candidate
removes 900 and 900 *does* appear in the evidence — yet the removal is right,
because the row is in DZD. A metric named "correct facts removed" would have
scored that as damage. Only opening the section decides it.

Equally, an abstention is not automatically a worse outcome than a trimmed
figure; it depends on whether the evidence supported an answer at all. Report
it, do not rank it.

## What the result is

`changed_decisions` — every figure one arm kept and the other removed, with its
case, each marked `"adjudication": "unreviewed"`. Someone opens the section the
figure came from and records whether the evidence establishes it. Until that
happens the comparison has found disagreements, not errors.

Ship or don't on the adjudicated list plus completeness and citation movement.
There is no threshold that decides it without reading the list.

## What this will not tell you

- Anything about markets the benchmark does not cover. Benelux and Nordic are
  68% of the corpus and have no cases.
- Anything about non-English answers beyond the cases that exist.
- Anything about arm 3.
- Anything about the publication changes; those are covered by the PostgreSQL
  checks and the unit tests.
