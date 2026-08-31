# AskVera Retrieval Authority Stack Evaluation

Date: 2026-08-31

## Decision

**Do not deploy the combined retrieval candidate.**

The implementation is complete, isolated behind disabled feature flags, and
passes the deterministic test suite. It improves held-out answer coverage and
deeper-rank recall, but it does not yet pass every promotion gate.

## Implemented candidates

1. Entity, question-type, and section-authority classification.
2. Authority-aware ranking using stored and runtime classification signals.
3. Parent-child retrieval expansion as a separately switchable factor.
4. Signal-based evidence confidence as a separately switchable factor.
5. Explicit target-market isolation for cross-market safety.

All new production-facing settings default to off. Current production behavior
is unchanged unless a candidate profile is explicitly enabled.

## Deterministic verification

- Unit tests: **761 passed**.
- Exact clone parity canary: **15/15 Current and 15/15 Candidate**.
- Authority-only canary after specificity correction: **15/15**, repeated three
  times without a Candidate regression.
- Parent-child isolated canary: **15/15**.
- Signal-confidence isolated canary after typo-query correction: **15/15**.
- Combined authority stack canary: **15/15**.

## Held-out comparison

The last completed 46-case, three-repeat held-out run produced:

| Metric | Current | Combined Candidate |
|---|---:|---:|
| Must-answer passes | 7/44 | 16/44 |
| Must-abstain passes | 2/2 | 1/2 |
| Overall expectation passes | 9/46 | 17/46 |
| Recall@1 | 4.55% | 4.55% |
| Recall@5 | 18.18% | 18.18% |
| Recall@10 | 20.45% | 29.55% |
| Recall@20 | 29.55% | 38.64% |
| MRR | 0.120814 | 0.117201 |

Interpretation:

- Answer coverage improved materially.
- Recall@10 and Recall@20 improved.
- Recall@1 and Recall@5 did not improve.
- Mean reciprocal rank declined slightly.
- The Candidate failed one required safe-abstention case and therefore was not
  eligible for promotion.

## Unsupported target-market correction

The failed safe-abstention case asked for a Manager minimum order in
Antarctica while the selected widget market was Canada. The combined Candidate
could borrow Canadian policy evidence.

The new candidate-only guard now applies this rule:

- A published policy market may use its own policy evidence.
- An explicitly named, unpublished market may use only an approved global
  directory record whose record country matches that market.
- If no matching approved directory record exists, retrieval returns no
  evidence and the assistant abstains.
- Selected-market policy evidence may not be borrowed for that request.

Three-repeat verification:

- Current: five Canadian documents remained present in every repeat.
- Candidate: zero documents and zero candidates in all three repeats.
- Candidate abstention: **3/3 structurally enforced**.
- Thailand global-directory canary: **passed**.
- UK Manager and international-sponsoring held-out checks: **passed**.

## Interrupted full rerun

A new full 46-case, three-repeat run was started after the target-market fix.
It was deliberately stopped at case 6 because Bedrock read timeouts affected
both Current and Candidate paths. The partial run is not used as benchmark
evidence and no aggregate result is claimed from it.

The partial run also exposed two response reliability concerns that must be
included in the next clean gate:

- one Candidate answer triggered the internal-retrieval-language validator;
- one Candidate generation timed out.

## Remaining promotion blockers

1. Establish a clean repeated full held-out run without timeout-contaminated
   comparisons, or report timeout outcomes as a separate reliability metric.
2. Improve first-result ranking. The current Candidate gains are concentrated
   below rank 5.
3. Review and correct any fixture labels proven inconsistent with the source
   document, without changing labels merely to improve Candidate scores.
4. Add response-quality and model-timeout gates alongside retrieval metrics.
5. Rerun safety, numeric validation, multilingual, locale isolation, and final
   answer gates on the exact promotion commit.
6. Deploy only when all required gates pass together.

## Production status

- No production feature flag was enabled.
- No production index was changed.
- No EC2 deployment was performed.
- Current production retrieval remains active.

