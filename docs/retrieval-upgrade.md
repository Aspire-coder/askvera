# AskVera Retrieval Upgrade Notes

## Baseline kept live

- The live provider remains `opensearch_section`.
- The current production OpenSearch index and vectors are unchanged.
- Exact section references continue to use the existing lookup path.
- No embedding model or production index change is included in this work.
- All new retrieval experiment switches default to `false`.

## Additive foundations

- Glossary entries are bounded and validated before they can affect query expansion.
- Model output limits are separated by purpose: planning, support routing, evidence selection, and translation.
- Offline evaluation now reports comparison count, same-section rate, evidence overlap, confidence wins, latency percentiles, and country/language failure counts.
- RRF ranking and parent-section diversity are wired as controlled experiments behind disabled flags. Bounded neighbor expansion remains an isolated helper until reliable neighbor metadata is available.
- Startup validation rejects invalid experiment limits before a restart can proceed.

## Safe promotion path

1. Capture a locked baseline from the current `opensearch_section` path.
2. Run candidate behavior in shadow mode against a separate `OPENSEARCH_VNEXT_INDEX`.
3. Compare retrieval quality by country and language, including citations, locale isolation, latency, and cost.
4. Require the configured promotion thresholds for same-section match, evidence overlap, and latency.
5. Run multilingual regression cases and review low-confidence answers before enabling any flag.
6. Promote one experiment at a time, with a documented rollback to the current provider and index.

## Offline comparison command

The comparison report can be JSON, JSONL, or an object containing a `comparisons`
or `records` array. Run it against a saved shadow sample:

```text
python scripts/evaluate_retrieval_shadow.py shadow-comparisons.json \
  --require-locale-gates --enforce-gate \
  --output retrieval-report.json
```

The report includes overall and per-country/language metrics for section match,
evidence overlap, confidence wins, p50/p95 shadow latency, input/output tokens,
estimated cost, and failure categories. Cost is reported only when the input
records contain token/cost fields; the evaluator does not invent pricing.

`--enforce-gate` is intended for CI or a promotion review. It does not change
the live answer path and should be run on a separate vNext comparison sample.

## Available but disabled by default

- RRF ranking
- Parent-section diversity
- Neighbor-context expansion
- Semantic caching
- A new embedding provider or index

The first two are connected to the OpenSearch section provider but remain disabled unless their settings are explicitly enabled. Neighbor expansion and semantic caching remain isolated experiments. UAT behavior is preserved until an approved comparison shows that a specific change improves quality without harming locale isolation, safety, latency, or cost.

## Verification note

The local runtime used for this review can compile the modified Python files and check repository whitespace, but it does not contain the full test dependencies. The complete pytest suite must pass in CI or a fully provisioned development environment before any experiment is enabled or deployed.
