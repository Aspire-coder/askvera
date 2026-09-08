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

## The pilot, chosen rather than taken from the top

The first six turns in fixture order are **five scope refusals and one
answer**. A grounding rule judged against refusals is measured on answers that
contain nothing for it to judge, so `--max-turns 6` alone would have produced a
result about nothing.

Six answerable numeric cases, chosen to cover the mechanisms the rule touches:

| Case | Why it is in the pilot |
|---|---|
| `algeria-delivery-cost` | 900 DZD; a unit adjacent to the figure, the dominant shape in this corpus |
| `reunion-delivery-cost` | `6EUR`, unit glued to the digits |
| `france-minimum-order` | `150EUR` glued, in a record naming two currencies |
| `algeria-repeat-order-minimum` | `5 000 DZD`, grouped thousands |
| `dk-fbo-support-fee-scope` | a Nordic market whose documents are byte-identical across DK/SE/NO/FI |
| `algeria-existing-fbo-order-minimum-role` | role-conditioned, and never validated live |

Six single-turn cases, so 6 turns per repeat.

```bash
python scripts/run_grounding_comparison.py --freeze out/frozen.json --load-ssm \
    --i-have-approval-for-paid-model-calls --max-turns 18 --repeat 3 \
    --case algeria-delivery-cost \
    --case reunion-delivery-cost \
    --case france-minimum-order \
    --case algeria-repeat-order-minimum \
    --case dk-fbo-support-fee-scope \
    --case algeria-existing-fbo-order-minimum-role
```

Start with `--repeat 1 --max-turns 6`, read the measured `usage` and the
console spend, then decide whether to continue. Continuing means repeating
those same six turns twice more - 12 further turn executions - not completing
the full fixture. `--resume` continues the same file; without it the harness
refuses to write over an existing capture.

## Commands

```bash
git worktree add ../askvera-main main

python scripts/run_grounding_comparison.py --preflight

# paid, bounded, resumable - see the pilot above for the case list
python scripts/run_grounding_comparison.py --freeze out/frozen.json --load-ssm \
    --i-have-approval-for-paid-model-calls --max-turns 6 --repeat 1 --case ...

python scripts/run_grounding_comparison.py --score out/frozen.json \
    --app-root ../askvera-main --out out/main.json
python scripts/run_grounding_comparison.py --score out/frozen.json \
    --app-root . --out out/candidate.json
python scripts/run_grounding_comparison.py --compare out/main.json out/candidate.json
```

## What is captured, and where

At the boundary immediately before numeric repair, through a hook the
orchestrator calls there. That is the input two repair rules must be compared
over.

It is deliberately **not** the pipeline's final response, and not the model's
raw output either. Nine steps run between generation and repair and more run
after it - restoration, formatting, governance - so the final response is a
different string, and an earlier version of this harness that read it would
have compared the wrong thing. Grounding is **not** disabled during capture:
every safeguard runs as in production and the hook only observes. The hook is
`None` in every process that does not install it.

## Turn accounting, checkpointing and resume

**Turn identity comes from the conversation runner, not from the capture hook.**
A turn that refuses early, or answers from cache, never reaches numeric repair
and so never fires the hook. Counting hook calls as turns gave a later answer
an earlier turn's expectation, undercounted requests against `--max-turns`, and
let the last captured turn mark a conversation complete when its real final
turn never was.

**Turn events.** Every request emits a `started` event before it runs and a
`completed` or `failed` event after, recorded by wrapping `handle_chat` in the
measurement process. So a turn is counted as attempted the moment it begins,
whether it refuses, fails or never returns. The capture reports
`turns_started`, `turns_completed`, `turns_failed` and `turns_unaccounted` -
the last should be zero on a clean run, and is non-zero if a request vanished.

Counting captures instead, as the previous exception path did, missed refusals
that preceded a failure and missed the failed request itself.

**Checkpointing** is per event, written as each turn starts and ends, and the
file is **replaced atomically** - written to a temporary file, fsynced, then
`os.replace`d. Writing in place meant an interrupted write truncated the file
that already held good turns.

Evidence captured for an interrupted attempt is kept, positioned by its
`started` event rather than by the order captures arrived - those differ the
moment an earlier turn refuses. Those records are `superseded` and never
scored: a partial chain is history, not a thing to measure.

**Each turn's evidence is written with its completion event**, not after the
conversation returns. Previously the completion event persisted while the
captured text stayed in memory until the chain finished, so a kill during a
later turn lost every earlier turn's answer - the event survived and the thing
it described did not.

**What is still not survivable:** a hard kill *inside* a turn, between the
model responding and that turn's record being written. That window is one
function call wide, and it is not zero.

**Resume validates provenance before any model call** - fixture hash, harness
commit, index, model id, chunk profile, the generation-pointer flag and a
corpus signature. It refuses across a dirty working tree, because the commit
can match while the code does not.

The pointer flag is included because it changes which documents retrieval can
see at all. The corpus signature is included because an index *name* is a
label: the same name can hold different content an hour later.

**The signature fingerprints the authority, not the index.** With the pointer
enabled that authority is `knowledge_active_generations` - the table
`_generation_filters` reads - so the signature is that mapping plus the active
section count. An earlier version aggregated `ingestion_id.keyword` in
OpenSearch and was wrong twice over: the index maps `ingestion_id` as a
keyword, so `ingestion_id.keyword` does not exist and the aggregation returned
nothing *silently*; and even written correctly it covered every indexed
generation rather than the active ones, so switching the pointer between two
generations that are both already indexed would have left the signature
unchanged while changing every answer for that market.

A resume where the signature reads `unavailable` is refused - two unknowns are
not a match.

**The corpus must be held still for the duration of the experiment.** The
signature detects a change; it cannot prevent one, and a change between arms
invalidates the comparison rather than merely interrupting it.

## Size

The fixture is **17 cases but 19 turns**: `belgium-then-germany-market-continuity`
replays two prior turns and then asks its own question, so it costs three
executions. An earlier estimate counted cases and called them calls.

| | turns | × repeat 3 |
|---|---:|---:|
| full fixture, freeze (one arm) | 19 | 57 turn executions |
| the pilot above, freeze (one arm) | 6 | **18 turn executions** |
| end-to-end, later, two arms, full fixture | 19 | 114 turn executions |

57 is correct for one full three-repeat freeze. It counts turns, not model
calls.

## Cost, and why a turn limit is not a budget

`--max-turns` bounds turns. A turn is several model calls, so it does not bound
spending. Stages that may call a model, per turn:

| Stage | Method | Always? |
|---|---|---|
| query embedding for vector search | `invoke_model` | yes |
| LLM query planner (`_planned_retrieval_plan`) | `converse` | when planning is enabled |
| LLM evidence selector (`_select_evidence_rows`) | `converse` | when there are rows to select |
| global-document query translation (`_global_search_query`) | `converse` | non-English or global scope |
| conversation intent verification (`_verified_conversation_intent`) | `converse` | follow-up turns |
| answer generation (`BedrockProvider.generate`) | `converse` | yes |
| candidate narrowing / guardrail rephrasing | `converse` | only under candidate flags |
| generation retry | `converse` | on a failed validation |

**Both invocation methods are instrumented.** An earlier version wrapped
`converse` only, so every embedding - one per turn, on the `invoke_model` path
in `services/embeddings.py` - was missing from the totals. The claim that it
covered "retries and every stage" was wrong and is withdrawn.

What the capture now reports under `usage`:

| Field | Meaning |
|---|---|
| `by_model` | calls and tokens per model id, because a rate applies to a model |
| `application_calls` | how many times the code asked Bedrock for something, counted **before** the request |
| `successful_calls` / `failed_calls` | how those calls ended |
| `http_attempts` | how many requests botocore actually sent |
| `sdk_retry_attempts` | the difference - retries the SDK made inside one call |
| `calls_without_reported_tokens` | embeddings, whose usage is not in the response envelope |

Counting the call *after* the request was wrong in the case that matters most:
a request that exhausted its retries and failed reported zero application calls
and three HTTP attempts, so the call vanished from the cost and every attempt
looked like a retry of nothing. A failed call may still have been billed for
input, so it is counted and reported separately rather than dropped.

**Two things this still cannot price.** Embedding token usage is not returned
by `invoke_model`, so those calls are counted and their tokens are not - read
them from the console. And a rate card is needed to turn tokens into money; I
do not have one.

If instrumentation cannot be installed the run **fails** rather than reporting
zero. A silent zero reads as "this costs nothing", which is the opposite of
what a pilot is for.

1. `--preflight` - free.
2. `--repeat 1 --max-turns 6` on the pilot list. Read `usage` from the capture
   and the spend from the Bedrock console for that window.
3. Multiply by the remaining turns, agree a cap, then continue with `--resume`.

**A spending cap is a decision, not a flag.** Nothing here can stop Bedrock
charging. `--max-turns` plus a measured call rate is what makes a bound
meaningful, and step 2 exists to produce that rate.

## Provenance

Every capture records the harness commit, whether the tree was dirty, the
fixture hash, the OpenSearch index, the model id, the chunk profile and the
generation-pointer flag. Scored arms carry it through, and `--compare` reports
both. A result that cannot be tied to the code and index that produced it is
not evidence of anything.

## Metrics

Every count is mechanical. None of them labels a figure correct or invented.

Reported in two blocks, because only one of them compares arms.

**`repair`** - a pure function of the frozen input, so it differs between arms
only because the rule differs. This is the comparison.

| Metric | What it counts |
|---|---|
| `figures_removed` | figures this arm's rule removed |
| `removed_and_present_in_evidence` | of those, the ones whose string occurs in a retrieved section |
| `removed_and_absent_from_evidence` | of those, the ones that do not occur at all |

**`pre_repair_sample_characteristics`** - missing required text, forbidden
text, uncited governing sections, abstentions, measured on the **pre-repair**
text. That is not what a reader sees: repair, restoration, formatting and
governance all run after the capture point. These numbers describe the captured
sample, are identical for both arms by construction, and compare nothing. Each
record also keeps `final_answer`, the text that turn actually returned, so
delivered answer and citation quality can be measured - by the separate
end-to-end run, not from this block.

**`skipped`** - turns excluded from scoring, and why: `superseded` (records
from an interrupted attempt) and `did_not_reach_repair` (refusals and early
returns, which have no evidence for a repair rule to judge).

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
