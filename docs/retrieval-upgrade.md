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
- RRF, parent-section diversity, and bounded neighbor expansion are isolated helpers for controlled experiments. They are not wired into the live path.
- Startup validation rejects invalid experiment limits before a restart can proceed.

## Safe promotion path

1. Capture a locked baseline from the current `opensearch_section` path.
2. Run candidate behavior in shadow mode against a separate `OPENSEARCH_VNEXT_INDEX`.
3. Compare retrieval quality by country and language, including citations, locale isolation, latency, and cost.
4. Require the configured promotion thresholds for same-section match, evidence overlap, and latency.
5. Run multilingual regression cases and review low-confidence answers before enabling any flag.
6. Promote one experiment at a time, with a documented rollback to the current provider and index.

## Not enabled by this change

- RRF ranking
- Parent-section diversity
- Neighbor-context expansion
- Semantic caching
- A new embedding provider or index

These remain deliberate experiments. UAT behavior is preserved until an approved comparison shows that a specific change improves quality without harming locale isolation, safety, latency, or cost.

## Verification note

The local runtime used for this review can compile the modified Python files and check repository whitespace, but it does not contain the full test dependencies. The complete pytest suite must pass in CI or a fully provisioned development environment before any experiment is enabled or deployed.
