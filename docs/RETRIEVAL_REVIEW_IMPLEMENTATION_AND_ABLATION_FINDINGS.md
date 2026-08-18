# Retrieval Review Implementation and Ablation Findings

Date: 2026-08-18
Scope: read-only evaluation tooling and same-index retrieval experiments
Production retrieval: unchanged

## Executive conclusion

The three external reviews are directionally correct. The strongest recommendation is to improve the evaluation discipline before promoting another retrieval profile. The current 76-question benchmark is useful for regression detection, but it is too small to establish a reliable production improvement by itself.

The experiments completed here do **not** justify promoting the selector or glossary changes as a new ranking profile. They do identify a useful glossary signal, but the effect is small and statistically inconclusive on the current sample. The selector-only experiment showed no Recall@1 gain and one Recall@5 regression.

## Baseline reconciliation correction

The phrase **Current** in the original selector-only table was too broad. It describes the current-side control inside that specific paired run, not the locked production reference used by the earlier promotion gates.

The earlier 84.48% production-selector reference and the newer selector-only run were not executed with identical planner/ranking controls. In particular, the newer selector-only checkpoint records a different search-query count from the earlier shared baseline, consistent with glossary-enabled planning being active in the newer run. The earlier same-index control was also created before the explicit current-selector flag was added.

Therefore:

- 84.48% Recall@1 remains the locked promotion reference until a clean, manifest-recorded rerun replaces it.
- The 82.76% selector-only control result must not be interpreted as a production regression or as proof that production silently changed.
- The selector-only result is valid only as a within-run paired comparison under its recorded flags.
- Cross-document comparisons require the same index, planner version, glossary mode, selector mode, labels, and case IDs.

This correction does not reverse the promotion decision; it makes the evidence boundary explicit.

## What was implemented

### Reproducible analysis

`[scripts/analyze_retrieval_evaluation.py](../scripts/analyze_retrieval_evaluation.py)` now produces:

- SHA-256 hashes for the checkpoint and labels;
- Git commit, timestamp, index, planner and profile metadata when available;
- Recall@1, @3, @5 and @10 with Wilson 95% confidence intervals;
- mean reciprocal rank;
- exact paired two-sided McNemar tests at each cutoff;
- case-level baseline/candidate comparisons;
- country, language, intent and difficulty-segment metrics;
- a companion CSV for segment review.

### Benchmark governance

`[scripts/split_retrieval_benchmark.py](../scripts/split_retrieval_benchmark.py)` creates deterministic train, validation and holdout assignments while keeping related questions together by locale and expected evidence. The current reviewed set contains 65 approved labels, 48 evidence groups, and is split into 45 train, 11 validation and 9 holdout rows.

This is a starting split, not yet a sufficient benchmark. The next target is at least 200 reviewed questions with a protected holdout set.

### Ablation correctness

The evaluator now supports explicit controls for:

- current production selector enabled during a same-index comparison;
- current glossary disabled while the candidate glossary is enabled;
- planner-cache keys that include glossary mode.

The last change fixed a real confound: the paired planner cache previously keyed only on question, country and language, which could make two glossary modes reuse the same plan. The corrected run was executed after this fix.

## Experiment results

All results below use the same production OpenSearch index, the same 76 rated interactions, and the same 58 cases with approved section labels. No documents, embeddings, production settings or live records were changed.

### Selector-only within-run comparison

Selector-enabled control versus candidate selector profile within the same run:

| Metric | Current | Candidate |
|---|---:|---:|
| Recall@1 | 82.76% (48/58) | 82.76% (48/58) |
| Recall@3 | 94.83% (55/58) | 94.83% (55/58) |
| Recall@5 | 100.00% (58/58) | 98.28% (57/58) |
| Recall@10 | 100.00% (58/58) | 98.28% (57/58) |
| MRR | 0.8905 | 0.8842 |

Paired result: no Recall@1 changes; at Recall@5, one case moved from correct to incorrect and none moved in the opposite direction. Exact McNemar p=1.0 because the sample is too small for this one-case difference to establish significance.

Decision: **do not promote on retrieval recall**. The selector may still help answer grounding or evidence presentation, but that requires answer-level evaluation under the same contract.

### Glossary-only

The current side intentionally had glossary disabled and the candidate side had the reviewed glossary enabled. This isolates the direction of the glossary change; it is not a production-versus-candidate score because the control is deliberately weaker than production.

| Metric | No-glossary control | Glossary candidate |
|---|---:|---:|
| Recall@1 | 25.86% (15/58) | 29.31% (17/58) |
| Recall@3 | 68.97% (40/58) | 72.41% (42/58) |
| Recall@5 | 77.59% (45/58) | 82.76% (48/58) |
| Recall@10 | 77.59% (45/58) | 82.76% (48/58) |
| MRR | 0.4672 | 0.4974 |

Paired result at Recall@5: four cases improved and one regressed; exact McNemar p=0.375. This is promising directionally but not conclusive. The experiment also confirms that glossary expansion alone is not enough to make the overall retrieval path promotion-ready.

## Interpretation of the reviews

The reviews correctly identify these as required before promotion:

1. Track exact case identities, not only aggregate totals.
2. Separate document recall from section recall.
3. Run selector, glossary, reranking and authority changes as independent ablations.
4. Add country, language, intent and failure-mode breakdowns.
5. Use confidence intervals and paired tests.
6. Grow the benchmark and protect a holdout set.
7. Evaluate answer quality with the same evidence contract for every pipeline.
8. Add cost, latency decomposition, stability and rollback gates.

The reviews are also right to defer HyDE and learned ranking until the seven zero-evidence cases and query-planner behavior are diagnosed. HyDE must remain an optional candidate-query generator only; it must never become evidence or cross locale boundaries.

## What is still not proven

- The seven no-result questions in the reviewed checkpoint are now classified in `outputs/interaction_quality/zero_evidence_root_cause.csv`: all seven are intentional routes, not knowledge-retrieval misses. They consist of one medical claim, three assistant/meta requests and three off-topic requests.
- A future diagnostic run must classify any genuine `knowledge_no_evidence` rows separately as threshold, planner, glossary, metadata, or corpus-gap failures.
- The current benchmark does not provide enough labels for reliable country/language conclusions.
- The answer contract has not been run symmetrically for current and candidate in these two ablations.
- No claim is made that the candidate improves production answer quality.
- No production deployment or index mutation was performed.

## Recommended next sequence

1. Diagnose the seven zero-evidence cases from raw pre-filter hits, planner queries, glossary queries and metadata filters.
2. Expand labels to 200+ questions with acceptable evidence sets, not only one exact section ID.
3. Create train, validation and locked holdout manifests with label review ownership.
4. Run answer-level current-versus-candidate evaluation under the identical evidence contract.
5. Add repeated-run stability, latency components, Bedrock cost and failure budgets.
6. Only then consider a shadow deployment and promotion gate.

## Artifacts

- Selector checkpoint: `outputs/interaction_quality/same-index-selector-only-rated.jsonl`
- Selector analysis: `outputs/interaction_quality/same-index-selector-only-rated-analysis.json`
- Glossary checkpoint: `outputs/interaction_quality/same-index-glossary-only-rated-v2.jsonl`
- Glossary analysis: `outputs/interaction_quality/same-index-glossary-only-rated-v2-analysis.json`
- Benchmark split: `outputs/interaction_quality/retrieval-benchmark-splits-rated.csv`
- Existing implementation record: `[docs/RETRIEVAL_COMPLETE_IMPLEMENTATION_AND_EVALUATION.md](RETRIEVAL_COMPLETE_IMPLEMENTATION_AND_EVALUATION.md)`
