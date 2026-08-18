# AskVera Retrieval: Complete Implementation and Evaluation Record

Date: 2026-08-18
Status: Implemented, evaluated, and documented. Production retrieval was not replaced.

This document is the consolidated record of the retrieval work completed in this development cycle. It explains the existing production path, every experimental change, how the experiments were evaluated, what improved, what was rejected, what remains, and what must happen before deployment.

## 1. Final decision

The current production retrieval path remains active.

The experimental changes are isolated behind evaluator profiles and feature flags. No production OpenSearch index was modified, no production retrieval flag was enabled, no Redis cache version was changed, and no EC2 deployment was performed for these retrieval experiments.

The best experimental result improved first-five coverage, but did not improve first-result accuracy enough to pass the promotion gate. The Bedrock reranker was also tested and rejected because it reduced retrieval quality despite being fast.

## 2. What the production retrieval system does today

AskVera uses `OpenSearchSectionProvider` as the primary retrieval provider.

The live flow is:

```text
User question
  -> intent and conversation routing
  -> query planning
  -> optional exact section lookup
  -> country and language filtered BM25 search
  -> country and language filtered vector search
  -> optional global-directory search
  -> merge and score candidates
  -> minimum-score filtering
  -> top approved sections
  -> citations and answer generation
```

The production path includes these protections:

- Country and language filtering
- Optional English fallback according to configuration
- Active document-generation filtering
- Active-status filtering
- Exact section lookup for explicit references such as `Section 19.45`
- Keyword and vector search
- Global-document retrieval for approved global directories and global FAQs
- Source and section scoring
- Minimum retrieval score filtering
- Approved-document citations
- Intent routing for support, medical, off-topic, and assistant-meta requests
- Evidence and numeric validation in the answer path

The user-visible provider remains controlled by the established production settings. Experimental flags do not automatically affect it.

## 3. Current retrieval versus experimental retrieval

Both paths use the same provider implementation. The difference is the index and the optional stages enabled when the provider is constructed.

| Capability | Current production path | Experimental path |
|---|---|---|
| Index | `OPENSEARCH_INDEX` | Explicit experimental index, or production index only during read-only rank ablation |
| User-visible | Yes | No |
| Query planner | Enabled | Enabled |
| Locale and generation filters | Enabled | Enabled |
| BM25 search | Enabled | Enabled |
| Vector search | Enabled | Enabled |
| Exact section lookup | Enabled | Enabled |
| Global documents | Enabled when the planner routes there | Enabled when the planner routes there |
| Glossary expansion | Production setting | Explicit experiment profile |
| Reciprocal-rank fusion | Disabled in production | Explicit experiment profile |
| Authority ranking | Disabled in production | Explicit experiment profile |
| Bedrock reranking | Disabled in production | Explicit experiment profile |
| Evidence selector | Production setting | Explicit experiment profile |
| Parent diversity | Disabled in production | Explicit experiment profile |
| Neighbor expansion | Disabled in production | Explicit experiment profile |
| Answer generation | User-visible | Not run for retrieval-only benchmarking |

## 4. Important index finding

An isolated r5 index was created as a content clone of the production index. The document count and content hashes matched production, but rebuilding the approximate vector graph changed nearest-neighbor results.

This meant that an isolated-index comparison could not prove whether a ranking change helped. It mixed two variables:

1. The intended ranking change
2. Different approximate vector-search behavior

The evaluation method was therefore changed to a true same-index ranking ablation. In that mode, both current and candidate paths use:

- The same production index
- The same query plan
- The same raw OpenSearch responses
- The same locale and generation filters

Only the candidate ranking stages differ. This is the reliable comparison used for the final experiments.

## 5. Redis cache investigation

Redis was investigated because stale answers could hide retrieval changes in the live application.

The evaluation script does not call the live retrieval service and does not initialize the production answer cache. The benchmark therefore bypasses Redis and measures retrieval directly.

Redis can still affect a future live deployment. If the retrieval pipeline changes, the production answer-cache namespace or pipeline version must be rotated. The implementation and deployment guidance use `RETRIEVAL_PIPELINE_VERSION` for this purpose.

Cache rules for future retrieval deployment:

- Do not interpret a cached answer as proof that a new retrieval pipeline is active.
- Rotate the retrieval pipeline version when retrieval behavior changes.
- Keep the current cache schema and answer cache isolated from experimental evaluation.
- Verify both cache misses and fresh uncached questions after deployment.

## 6. Query-planning and expansion work

The first analysis identified seven historical questions without expected evidence. The investigation separated possible causes instead of assuming that reranking would improve recall.

The failure categories were:

- Candidate exists but was removed by a score threshold
- Query planner did not create a useful search formulation
- Glossary or terminology coverage was missing
- Content was genuinely absent from the index
- Country, language, or generation metadata excluded valid content
- Request was intentionally routed away from knowledge retrieval

The bounded glossary expansion added reviewed terminology for:

- Recognized Manager spelling variants
- Assistant Manager spelling variants
- Approved abbreviations such as RM
- Case Credit and activity terminology
- German activity and Case Credit phrasing
- FBO application, enrollment, and registration wording
- Sponsor-change and responsor terminology in German, Italian, Spanish, French, Dutch, and English

The expansion is reusable terminology configuration. It is not a list of hardcoded answers and does not bypass country or language filters.

## 7. Candidate and ranking work

### 7.1 Same-index ablation harness

The evaluator now supports explicit rank profiles such as:

- `rank-baseline`
- `rank-rrf`
- `rank-authority`
- `rank-selector`
- `rank-selector-authority`
- `rank-rerank`
- `rank-rerank-authority`

The evaluator shares query plans, translation results, and exact raw search responses between paired current and candidate runs. It captures candidate evidence before final selection so failures can be diagnosed.

### 7.2 Reciprocal-rank fusion

RRF combines keyword and vector rankings before final scoring.

Result:

- Deterministic Recall@1: 41.38%
- Deterministic Recall@5: 91.38%
- Deterministic Recall@10: 91.38%

Decision: rejected. It improved the deterministic control but remained below the production reference and failed the first-five gate.

### 7.3 Authority-aware ranking

Authority metadata was added to ingestion and index mappings:

| Authority class | Chunk types |
|---|---|
| `governing` | `section`, `section_part`, `definition` |
| `supporting` | `list_item`, `numeric_fact`, `table_row` |
| `navigational` | outline and other navigation chunks |

For the existing index, authority is inferred from `chunk_type` so an index rebuild is not required for evaluation.

The ranker gives narrow structural preference to governing or definition chunks when the question is clearly asking for a definition, rule, requirement, or procedure. It does not encode policy answers.

Decision: rejected as a standalone candidate. Authority improved some deterministic first-result cases but remained below the production reference.

### 7.4 Model evidence selector

The Bedrock evidence selector receives only already-retrieved candidates. It may reorder or select candidates, but it cannot search outside the candidate set or invent evidence.

If the selector fails, returns invalid ranks, or returns no usable selection, the original ranking is preserved.

The selector produced the strongest current benchmark behavior, but it is model-based and has measurable latency. It remains experimental until evaluated against the expanded reviewed benchmark.

### 7.5 Bounded query expansion plus selector

This combined experiment produced:

- Recall@1: 82.76%
- Recall@3: 96.55%
- Recall@5: 100%
- Recall@10: 100%
- Mean reciprocal rank: 0.8948
- p95 latency: 3.25 seconds
- Retrieval errors: 0

This fixed the previous first-five miss for the German question about how four Case Credits are composed. All 58 exact-section-labeled cases had their expected section within the first five results.

However, the result did not beat the production Recall@1 reference of 84.48%, and latency exceeded the 1.5-second gate.

Decision: rejected for promotion, but the expanded candidate generation is worth preserving for future ranking experiments because it achieved 100% Recall@5.

### 7.6 Bedrock managed reranker

The Cohere Rerank 3.5 model was tested over the unchanged top 20 candidates from the production index.

Reranker alone:

- Recall@1: 58.62%
- Recall@3: 86.21%
- Recall@5: 94.83%
- Recall@10: 94.83%
- Incremental p95 latency: 0.75 seconds

Authority hints before reranking:

- Recall@1: 65.52%
- Recall@3: 86.21%
- Recall@5: 94.83%
- Recall@10: 94.83%
- Incremental p95 latency: 1.39 seconds

The reranker was fast enough, but it removed valid expected sections from the first five and substantially reduced first-result accuracy.

Decision: rejected. The profiles remain disabled and available only for reproducible future experiments.

## 8. Failure diagnosis results

For the best expanded-query candidate:

- 48 of 58 exact-section-labeled cases placed the expected section first
- 10 of 58 placed it at rank 2 through 5
- 0 cases had a matching candidate omitted from the final five
- 0 cases were classified as no matching candidate
- 0 cases were classified as metadata exclusion failures

This is important: the remaining problem is first-result ordering, not broad corpus recall.

For the managed reranker:

- 38 of 58 exact-section-labeled cases placed the expected section first in the authority-assisted run
- 17 were at ranks 2 through 5
- 3 expected sections were omitted from the final five

That is why the reranker was rejected even though its latency was acceptable.

## 9. Metadata and ingestion improvements

The production index audit confirmed that the current records already contain:

- Document version
- Effective date
- Chunk type
- Parent section ID
- Ingestion ID

The audit found no explicit authority metadata on the existing records. The ingestion extractor and OpenSearch loader now support `authority_level` for future ingestion. Existing records remain backward-compatible through inferred authority.

No production records were rewritten as part of this work.

## 10. Benchmark and review tooling

The historical evaluation set contains:

- 1,391 total interaction records
- 76 rated cases
- 65 document-labeled cases
- 58 exact-section-labeled cases
- 26 country/language groups represented in the benchmark expansion work

A stratified queue of 135 additional questions was generated to reach a 200-question reviewed benchmark.

The queue intentionally does not invent expected evidence. Each additional question must be reviewed and assigned:

- Expected document
- Expected section, where applicable
- Whether the question is knowledge retrieval or intentional routing
- Country and language correctness
- Any numeric or citation requirements

Until those labels are approved, the 135 questions cannot be used as promotion ground truth.

## 11. Promotion gates

An experimental retrieval candidate must satisfy every gate:

- Recall@1 strictly greater than 84.48%
- Recall@5 at least 98.28%
- Recall@10 at least 98.28%
- No document-recall regression
- No new retrieval errors
- No country or language isolation regression
- End-to-end p95 retrieval latency no greater than 1.5 seconds
- The reviewed benchmark expanded to 200 questions
- Fresh uncached production smoke tests pass

The automated gate is implemented in `scripts/check_retrieval_promotion.py`. A failed gate returns a non-zero exit code and does not change runtime settings.

## 12. Verification completed

The following checks passed:

- Full Python test suite using a project-local pytest temporary directory
- Retrieval profile tests
- Bedrock reranker tests
- Evidence failure-diagnostic tests
- Promotion-gate tests
- Review-queue tests
- Ingestion authority metadata tests
- OpenSearch retrieval tests
- Flake8 on changed retrieval, ingestion, evaluation, and test files
- `git diff --check`

The default pytest temporary directory on this Windows environment produced access-denied warnings, so the full suite was rerun with a workspace-local temporary directory. The tests themselves passed.

## 13. Files added or materially changed

### Retrieval and ranking

- `app/retrieval/opensearch_sections.py`
- `app/retrieval/providers.py`
- `app/retrieval/glossary.py`
- `app/retrieval/service.py`
- `app/retrieval/bedrock_reranker.py`
- `app/retrieval/vnext_quality.py`
- `app/retrieval/quality_dataset.py`
- `config/search_glossary.json`
- `config/settings.py`

### Ingestion and metadata

- `scripts/ingestion/extract_policy_sections.py`
- `scripts/ingestion/load_policy_sections_to_opensearch.py`
- `scripts/ingestion/README.md`
- `scripts/validate_config.py`

### Evaluation and diagnostics

- `scripts/evaluate_interaction_history.py`
- `scripts/diagnose_retrieval_failures.py`
- `scripts/build_retrieval_review_queue.py`
- `scripts/check_retrieval_promotion.py`
- `scripts/audit_opensearch_index_parity.py`
- `scripts/clone_retrieval_candidate_index.py`
- `scripts/rebuild_vnext_candidate_index.py`
- `scripts/compare_retrieval_evaluations.py`

### Tests

The retrieval changes include unit coverage for:

- Profile isolation
- Same-index evaluation safeguards
- Shared search and translation caches
- OpenSearch scoring and authority behavior
- Glossary behavior
- Ingestion authority metadata
- Reranker behavior and fail-open handling
- Failure diagnostics
- Promotion gates
- Benchmark queue generation
- Expected-evidence parsing and metrics

## 14. Existing reference documents

This complete record complements:

- [ASKVERA_CURRENT_AND_VNEXT_RETRIEVAL_CODE.md](ASKVERA_CURRENT_AND_VNEXT_RETRIEVAL_CODE.md) - code-level architecture and flow
- [RETRIEVAL_REMAINING_IMPROVEMENTS_FINDINGS.md](RETRIEVAL_REMAINING_IMPROVEMENTS_FINDINGS.md) - experiment findings and promotion decision
- [RETRIEVAL_VNEXT_SHADOW_ROLLOUT.md](RETRIEVAL_VNEXT_SHADOW_ROLLOUT.md) - rollout controls and operational guidance

## 15. Remaining work

The next step is not another production deployment. It is to complete the 200-question benchmark:

1. Review and label the 135 queued questions.
2. Separate train, validation, and holdout groups.
3. Preserve the expanded candidate generation that achieved 100% Recall@5.
4. Calibrate a lightweight ranker using the enlarged benchmark.
5. Compare it against the current model selector with repeated runs.
6. Run end-to-end shadow latency tests with fresh uncached requests.
7. Promote only if every gate passes.

Until then, the current production retrieval path is the approved path.
