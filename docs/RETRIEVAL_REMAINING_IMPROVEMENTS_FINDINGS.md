# Retrieval Remaining Improvements Findings

Date: 2026-08-18

## Decision

Keep the current production retrieval path unchanged.

The remaining improvements were implemented behind experimental controls and evaluated against the production OpenSearch index. The best new candidate recovered every reviewed expected section within the first five results, but it did not improve first-result accuracy and it exceeded the latency gate. It must not be promoted yet.

No production index, runtime flag, cache version, or deployment was changed during this work.

## Evaluation controls

- Current and candidate retrieval used the same production index and the same raw OpenSearch responses.
- The harness shares exact search responses between both sides so ranking changes can be isolated without rebuilding the vector graph.
- Model-based evidence selection is disabled in the deterministic control and enabled only in profiles that explicitly test it.
- Candidate results are fail-closed through an automated promotion gate.
- The evaluator bypasses the production answer cache. Redis therefore did not influence these measurements.

## Results

### Current production-selector reference

The representative current-path selector run produced:

- Section Recall@1: 84.48%
- Section Recall@5: 98.28%
- Section Recall@10: 98.28%
- One reviewed expected section missing from the first five results

### Deterministic reciprocal-rank fusion

RRF improved deterministic ranking over its paired no-selector control, but remained below the production reference:

- Section Recall@1: 41.38%
- Section Recall@5: 91.38%
- Section Recall@10: 91.38%

Decision: rejected.

### Authority-aware ranking

Authority metadata and backward-compatible authority inference were added. Authority-only ranking improved its paired deterministic Recall@1 by two cases, but remained materially below the production reference.

Authority plus model selection produced:

- Section Recall@1: 82.76%
- Section Recall@5: 98.28%
- Section Recall@10: 98.28%
- p95 latency: 3.57 seconds

Decision: rejected.

### Bounded query expansion plus model selection

The expansion covers reviewed spelling variants, approved abbreviations, German activity terminology, FBO application/enrollment phrasing, and localized sponsor-change terminology.

It produced:

- Section Recall@1: 82.76%
- Section Recall@3: 96.55%
- Section Recall@5: 100%
- Section Recall@10: 100%
- Mean reciprocal rank: 0.8948
- p95 latency: 3.25 seconds
- Retrieval errors: 0

This recovered the previous first-five miss for the German question about how four CC are composed. All 58 reviewed section cases now have expected evidence within the final five. Ten cases still place the expected section at ranks 2 through 5.

Decision: rejected because Recall@1 does not exceed 84.48% and p95 latency exceeds 1.5 seconds.

### Managed pairwise reranking on the production index

A purpose-built Bedrock Rerank 3.5 model was evaluated over the unchanged top
20 candidates. Both pipelines used the same query plan, production index, and
raw OpenSearch responses. This removes the vector-graph rebuild difference that
affected the earlier isolated-index rerank experiment.

Reranking alone produced:

- Section Recall@1: 58.62%
- Section Recall@3: 86.21%
- Section Recall@5: 94.83%
- Section Recall@10: 94.83%
- Incremental p95 latency in the paired run: 0.75 seconds
- Retrieval errors: 0

Authority hints before reranking produced:

- Section Recall@1: 65.52%
- Section Recall@3: 86.21%
- Section Recall@5: 94.83%
- Section Recall@10: 94.83%
- Incremental p95 latency in the paired run: 1.39 seconds
- Retrieval errors: 0

The authority hint improved first-result placement but did not recover the
three reviewed expected sections omitted from the final five. Both profiles
failed the Recall@1, Recall@5, and Recall@10 promotion gates.

Decision: reject the managed-reranker path. Do not tune it against the small
reviewed set and do not deploy it. The disabled `rank-rerank` and
`rank-rerank-authority` evaluator profiles remain available solely so the
result is reproducible on a larger future benchmark.

## Failure diagnosis

For the expanded-query candidate:

- Top rank: 48 of 58 reviewed section cases
- Final ranks 2 through 5: 10 of 58
- Matching candidate omitted from final five: 0
- No matching candidate: 0
- Metadata exclusion failures: 0

The remaining issue is first-result ordering, not corpus discovery or first-five recall.

## Implemented safeguards and tooling

- True same-index ranking ablations
- Shared translation and raw-search caches for paired evaluations
- Candidate evidence capture before final selection
- Failure classification into routing, final ranking, candidate omission, and no-candidate cases
- Explicit authority metadata for new ingestion, with fallback inference for the current index
- Automated promotion gates for Recall@1, Recall@5, Recall@10, document recall, errors, and latency
- Stratified review-queue generation for a 200-question benchmark
- Direct-execution support and unit tests for all new evaluation utilities

## Benchmark expansion status

The existing approved benchmark contains 65 document-labeled cases, including 58 with exact section labels. A stratified queue of 135 additional production questions was generated to reach 200 reviewed questions across 26 country/language groups.

Those 135 rows intentionally have no fabricated evidence labels. A human reviewer must identify and approve the expected document and section before they can be used as promotion ground truth.

## Promotion requirements

A candidate may be considered only when it satisfies all of the following on reviewed evidence:

- Section Recall@1 is strictly greater than 84.48%
- Section Recall@5 is at least 98.28%
- Section Recall@10 is at least 98.28%
- Document Recall@1 does not regress
- No new retrieval errors or country/language boundary regressions
- End-to-end p95 retrieval latency is no more than 1.5 seconds
- The expanded 200-question benchmark is human-labeled and passes

If a candidate is eventually deployed, rotate `RETRIEVAL_PIPELINE_VERSION` so Redis cannot serve answers generated by an older retrieval pipeline.

## Verification

- Full Python test suite passed using a project-local temporary directory.
- Flake8 passed for all changed retrieval, ingestion, evaluation, and test files.
- The promotion gate rejected the latest candidate as designed.

## Recommended next step

Do not add more broad query expansion and do not tune another ranker against
only 58 section-labeled questions. The lower-latency managed ranker has now been
tested and rejected. The next quality step is benchmark work, not another
production candidate:

1. Human-label the 135 queued questions to reach 200 reviewed cases.
2. Preserve the expanded candidate generation because it reached 100% Recall@5.
3. Use the enlarged benchmark to train or calibrate a deterministic lightweight
   ranker with separate train, validation, and holdout groups.
4. Compare it against the current selector using repeated runs to measure model
   variance.
5. Promote only after the full reviewed benchmark and end-to-end shadow latency
   pass every gate.
