# AskVera semantic answer cache

## Status

The semantic cache is implemented as an opt-in optimization. Live answer reuse is disabled by default. Shadow mode can safely populate and evaluate matches while always delivering the normal freshly generated answer.

The production rollout configuration uses `SEMANTIC_CACHE_ENABLED=false` and `SEMANTIC_CACHE_SHADOW_ENABLED=true`. These modes are mutually exclusive.

## Safe request flow

1. Validate the session, consent, market, language and role.
2. Scrub private information and apply input governance.
3. Check the existing versioned exact cache.
4. Run the current production retrieval and evidence-approval flow.
5. Search the semantic cache only among answers with the same country, language, role and evidence fingerprint.
6. Re-run output cleanup, validation and governance on a semantic hit.
7. On a miss or any cache/embedding failure, generate the answer through the existing backend.
8. Store only complete, cited answers above the configured confidence threshold.

This ordering means semantic caching cannot bypass current retrieval, active documents, country boundaries, role boundaries or output safety checks.

## Storage design

- Existing exact cache remains the fastest first check.
- Semantic entries use independently expiring Redis keys and a bounded sorted-set index.
- The raw user question is not stored. Each entry contains only its embedding, cache-safe response, evidence fingerprint and timestamps.
- The fingerprint includes document IDs, source URIs, versions, ingestion IDs, logical IDs, section IDs and a content digest.
- Namespace versions include knowledge, retrieval, routing, response, prompt, guardrail, answer-model and embedding-model versions.
- Expired or missing entries are removed from the index during reads.
- Similarity is calculated over a bounded candidate set. This is compatible with the current Valkey deployment without assuming an unverified vector-search module. Native Redis/Valkey vector search can replace this bounded lookup after the production engine capability is confirmed.

## Configuration

| Variable | Default | Purpose |
|---|---:|---|
| `SEMANTIC_CACHE_ENABLED` | `false` | Master switch. |
| `SEMANTIC_CACHE_SHADOW_ENABLED` | `false` | Observe matches but never serve semantic answers. |
| `SEMANTIC_CACHE_SCHEMA_VERSION` | `1` | Invalidates semantic namespaces when the storage contract changes. |
| `SEMANTIC_CACHE_THRESHOLD` | `0.96` | Minimum cosine similarity. |
| `SEMANTIC_CACHE_MIN_SCORE_MARGIN` | `0.02` | Rejects ambiguous matches with similarly scored, different answers. |
| `SEMANTIC_CACHE_MIN_CONFIDENCE` | `0.75` | Minimum source-answer confidence for storage. |
| `SEMANTIC_CACHE_MAX_CANDIDATES` | `64` | Maximum candidates evaluated per request. |
| `SEMANTIC_CACHE_MAX_ENTRIES` | `256` | Maximum entries retained per country/language/role namespace. |
| `SEMANTIC_CACHE_TTL_SECONDS` | `7200` | Per-entry lifetime. |
| `SEMANTIC_CACHE_MAX_VECTOR_DIMENSIONS` | `1536` | Upper bound for stored vectors. |
| `SEMANTIC_CACHE_EMBED_MODEL_ID` | current embedding model | Embedding model and namespace version input. |
| `SEMANTIC_CACHE_SHADOW_MIN_ANSWER_AGREEMENT` | `0.70` | Flags low-agreement shadow matches for review. |

Startup validation rejects missing Redis configuration and invalid thresholds, limits or TTLs when semantic caching is enabled.

## Observability

Responses identify `exact`, `semantic` or fresh behavior in safe metadata. Internal traces record shadow mode, would-hit state, similarity, answer/citation agreement, review status and estimated token savings. The audit pipeline receives the same comparison as a `SEMANTIC_CACHE_SHADOW` event. Embeddings, questions and cached answer text are not written to these diagnostics.

In shadow mode, a would-hit is never reported as a real cache hit and actual token savings remain zero because Claude still generates the delivered answer.

## Failure behavior

Redis errors, malformed entries and embedding-service failures are semantic misses. They never make the chat request fail and the normal backend remains authoritative.

## Required rollout gates

1. Keep the feature disabled while running an offline paraphrase benchmark across all countries and supported languages.
2. Review false-positive pairs manually, especially policy numbers, qualification levels, dates, negation and country-specific rules.
3. Require no country, role, language, citation, safety or retrieval regression.
4. Enable a small production canary and monitor semantic hit rate, fallback rate, helpfulness, false-positive reports, latency and cost.
5. Increase traffic only after the canary is reviewed. Disable immediately through `SEMANTIC_CACHE_ENABLED=false` if quality degrades.

The similarity threshold should be lowered only with benchmark evidence. A higher threshold reduces savings but is safer for regulated policy answers.
