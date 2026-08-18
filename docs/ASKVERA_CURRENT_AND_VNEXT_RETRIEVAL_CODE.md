# AskVera Current and vNext Retrieval Code Reference

Last verified against the local repository: 2026-08-18
Production baseline verified on 2026-08-18: `2c694f6` (`fix: recognize composed small-talk greetings`)
Status: vNext is an isolated evaluation/shadow pipeline. It has not replaced the current user-visible retrieval path.

## 1. Executive summary

AskVera does not maintain two completely separate retrieval implementations. Both paths use `OpenSearchSectionProvider`, which provides:

- country and language filtering;
- active-generation filtering;
- keyword/BM25 search;
- vector search;
- exact section lookup;
- optional global-directory retrieval;
- source scoring and confidence calculation; and
- approved-document citations.

The difference is how the provider is constructed and which optional stages are enabled.

| Capability | Current retrieval | vNext retrieval |
|---|---:|---:|
| Primary OpenSearch index | `OPENSEARCH_INDEX` | Separate `OPENSEARCH_VNEXT_INDEX` |
| User-visible | Yes | No, shadow/evaluation only |
| Query planner | Yes | Yes |
| Locale and generation filters | Yes | Yes |
| Keyword and vector retrieval | Yes | Yes |
| Local policy-aware scoring | Yes | Yes |
| Reviewed glossary expansion | Off by default | Enabled in the full evaluation profile |
| Reciprocal-rank fusion | Off | Enabled in the full evaluation profile |
| Bedrock reranking | Off | Optional, vNext only |
| Model-based evidence selector | Off | Enabled in the full evaluation profile |
| Parent-section diversity | Off | Enabled in the full evaluation profile |
| Neighbor/sibling expansion | Off | Enabled in the full evaluation profile |
| Evidence-contract retry and repair | Established answer path | Strengthened in vNext evaluation |
| Citation-aware numeric review | Established validator | Strengthened in vNext evaluation |

## 2. End-to-end flows

### Current retrieval

```text
Question
  -> query planner and intent routing
  -> exact section lookup when explicitly requested
  -> locale-filtered BM25 search
  -> locale-filtered vector search
  -> optional approved global-directory search
  -> merge and normalize scores
  -> policy-aware local scoring
  -> minimum-score filter
  -> top documents and citations
  -> user-visible answer generation
```

### vNext retrieval

```text
Same question and locale
  -> reviewed glossary expansion
  -> query planner and intent routing
  -> same exact/keyword/vector/global retrieval rules
  -> separate vNext index with smaller structure-aware chunks
  -> reciprocal-rank fusion of keyword and vector rankings
  -> optional Bedrock reranking
  -> model-based evidence selection
  -> parent-section diversity
  -> bounded sibling/neighbor expansion
  -> top documents and citations
  -> evidence contract and citation-aware numeric validation
  -> comparison/evaluation only; never replaces the primary result
```

## 3. Current retrieval code

The live service selects the configured primary provider and returns its result. Shadow work is submitted only after the primary result is fixed.

Source: `app/retrieval/service.py`

```python
class RetrievalService:
    def _default_provider(self) -> RetrievalProvider:
        return self._provider_for_name(settings.RETRIEVAL_PROVIDER)

    @staticmethod
    def _provider_for_name(
        provider_name: str,
        *,
        index_name: str | None = None,
        enable_bedrock_rerank: bool = False,
        experimental_features: bool = False,
        result_count: int | None = None,
        glossary_enabled: bool | None = None,
        evidence_selector_enabled: bool | None = None,
    ) -> RetrievalProvider:
        if provider_name == "section":
            return SectionSearchProvider()
        if provider_name == "opensearch_section":
            return OpenSearchSectionProvider(
                index_name=index_name,
                enable_bedrock_rerank=enable_bedrock_rerank,
                experimental_features=experimental_features,
                result_count=result_count,
                glossary_enabled=glossary_enabled,
                evidence_selector_enabled=evidence_selector_enabled,
            )
        return BedrockRetrievalProvider()

    def retrieve(
        self,
        message: str,
        country: str,
        language: str,
        role: str,
        correlation_id: str,
    ) -> RetrievalResult:
        provider = self._current_provider()
        result = provider.retrieve(
            message,
            country,
            language,
            role,
            correlation_id,
        )
        self._submit_shadow_comparison(
            message=message,
            country=country,
            language=language,
            role=role,
            correlation_id=correlation_id,
            primary_result=result,
        )
        return result
```

The current provider defaults to the established OpenSearch index and established feature settings.

Source: `app/retrieval/opensearch_sections.py`

```python
class OpenSearchSectionProvider:
    def __init__(
        self,
        index_name: str | None = None,
        *,
        enable_bedrock_rerank: bool = False,
        experimental_features: bool = False,
        result_count: int | None = None,
        glossary_enabled: bool | None = None,
        evidence_selector_enabled: bool | None = None,
    ) -> None:
        self.index_name = index_name or settings.OPENSEARCH_INDEX
        self.enable_bedrock_rerank = enable_bedrock_rerank
        self.experimental_features = experimental_features
        self.result_count = max(
            1,
            int(result_count or settings.OPENSEARCH_RESULT_COUNT),
        )
        self.glossary_enabled = glossary_enabled
        self.evidence_selector_enabled = evidence_selector_enabled
```

The current and vNext paths share the main retrieval method. Optional stages run only when their provider flags are enabled.

```python
def retrieve(
    self,
    message: str,
    country: str,
    language: str,
    role: str,
    correlation_id: str,
) -> RetrievalResult:
    del role
    search_plan = self._build_search_plan(
        message,
        country,
        language,
        correlation_id,
    )

    # Non-knowledge requests can be routed without policy retrieval.
    if search_plan.client_action:
        return RetrievalResult(
            documents=[],
            citations=[],
            confidence=1.0,
            metadata={
                "provider": "opensearch_section",
                "client_action": search_plan.client_action,
                "conversation_intent": "support_request",
            },
        )

    client = _client()
    text_hits: list[dict[str, Any]] = []
    vector_hits: list[dict[str, Any]] = []

    # Explicit references such as "section 4.7-b" receive an exact lookup.
    explicit_section_id = _section_reference(message)
    if explicit_section_id:
        exact_response = client.search(
            index=self.index_name,
            body=_exact_section_query(
                explicit_section_id,
                country,
                language,
            ),
        )
        text_hits.extend(exact_response["hits"]["hits"])

    # Each planned query runs through both lexical and semantic search.
    for search_message in search_plan.queries:
        text_response = client.search(
            index=self.index_name,
            body=_text_query(
                search_message,
                country,
                language,
                scope="locale",
            ),
        )
        vector_response = client.search(
            index=self.index_name,
            body=_vector_query(
                search_message,
                country,
                language,
                scope="locale",
            ),
        )
        text_hits.extend(text_response["hits"]["hits"])
        vector_hits.extend(vector_response["hits"]["hits"])

    # Global documents are searched only when the planner selects that scope.
    if search_plan.include_global_documents:
        global_query = self._global_search_query(
            message,
            language,
            correlation_id,
        )
        text_hits.extend(
            client.search(
                index=self.index_name,
                body=_directory_text_query(global_query),
            )["hits"]["hits"]
        )
        vector_hits.extend(
            client.search(
                index=self.index_name,
                body=_vector_query(
                    global_query,
                    country,
                    language,
                    scope="global",
                ),
            )["hits"]["hits"]
        )

    rows = self._merge_hits(text_hits, vector_hits, message)

    if self.enable_bedrock_rerank:
        rows = rerank_rows(message, rows, correlation_id=correlation_id)

    rows = self._select_evidence_rows(message, rows, correlation_id)
    rows = self._apply_parent_diversity(rows)
    final_rows = self._expand_neighbor_rows(
        client,
        rows,
        country,
        language,
        correlation_id,
    )

    documents = [
        self._document_from_row(row, score)
        for row, score in final_rows
        if score >= settings.SECTION_RETRIEVAL_MIN_SCORE
    ][: self.result_count]

    return RetrievalResult(
        documents=documents,
        citations=[document.to_source() for document in documents],
        confidence=_confidence_from_documents(documents),
        metadata={"provider": "opensearch_section"},
    )
```

The source excerpt above is shortened for readability. Error handling, metrics, detailed metadata, outline retrieval, and logging remain in the implementation.

## 4. Security and locale isolation shared by both paths

Country documents and global documents use separate filters. A country-policy query cannot silently retrieve another market's policy.

Source: `app/retrieval/opensearch_sections.py`

```python
def _scope_filter(
    country: str,
    language: str,
    scope: str,
) -> dict[str, Any]:
    if scope == "global":
        return {
            "bool": {
                "filter": [
                    {"term": {"access_scope": "global"}},
                    _language_filter(language),
                ]
            }
        }
    return {
        "bool": {
            "filter": [
                {
                    "terms": {
                        "country": sorted(
                            get_document_country_codes(country)
                        )
                    }
                },
                _language_filter(language),
            ]
        }
    }
```

Every query also filters to active records and, when generation pointers are enabled, the atomically published generation.

```python
"filter": [
    _scope_filter(country, language, scope),
    {"term": {"status": "active"}},
    *_generation_filters(country, language, scope),
]
```

This isolation must remain unchanged when vNext is eventually promoted.

## 5. vNext construction and isolation

vNext is created only with a separate index and explicit experimental settings.

Source: `app/retrieval/service.py`

```python
if (
    settings.RETRIEVAL_VNEXT_PROVIDER != "opensearch_section"
    or not settings.OPENSEARCH_VNEXT_INDEX
    or settings.OPENSEARCH_VNEXT_INDEX == settings.OPENSEARCH_INDEX
):
    return

shadow_provider = self._provider_for_name(
    settings.RETRIEVAL_VNEXT_PROVIDER,
    index_name=settings.OPENSEARCH_VNEXT_INDEX,
    enable_bedrock_rerank=settings.RETRIEVAL_VNEXT_RERANK_ENABLED,
    experimental_features=True,
    result_count=settings.RETRIEVAL_VNEXT_RESULT_COUNT,
    glossary_enabled=settings.RETRIEVAL_VNEXT_GLOSSARY_ENABLED,
    evidence_selector_enabled=(
        settings.RETRIEVAL_VNEXT_EVIDENCE_SELECTOR_ENABLED
    ),
)
```

The shadow result is measured but never returned to the user.

```python
def _run_shadow_comparison(..., primary_result: RetrievalResult) -> None:
    shadow_result = shadow_provider.retrieve(
        message,
        country,
        language,
        role,
        f"{correlation_id}-shadow",
    )

    comparison = {
        "primary_count": len(primary_result.documents),
        "primary_confidence": primary_result.confidence,
        "vnext_count": len(shadow_result.documents),
        "vnext_confidence": shadow_result.confidence,
        "top_result_matches": (
            _top_document_key(primary_result)
            == _top_document_key(shadow_result)
        ),
        "result_overlap": result_overlap,
    }

    record_retrieval_shadow_comparison(comparison)
```

The evaluator enforces the same separation.

Source: `scripts/evaluate_interaction_history.py`

```python
def _vnext_provider(profile: str) -> OpenSearchSectionProvider:
    if not settings.OPENSEARCH_VNEXT_INDEX:
        raise RuntimeError(
            "OPENSEARCH_VNEXT_INDEX is required for isolated vNext evaluation."
        )
    if settings.OPENSEARCH_VNEXT_INDEX == settings.OPENSEARCH_INDEX:
        raise RuntimeError(
            "vNext evaluation refused: OPENSEARCH_VNEXT_INDEX matches OPENSEARCH_INDEX."
        )

    features = _configure_vnext_profile(profile)

    return OpenSearchSectionProvider(
        index_name=settings.OPENSEARCH_VNEXT_INDEX,
        enable_bedrock_rerank=rerank_enabled,
        experimental_features=True,
        result_count=settings.RETRIEVAL_VNEXT_RESULT_COUNT,
        glossary_enabled="glossary" in features,
        evidence_selector_enabled="evidence_selector" in features,
    )
```

## 6. vNext improvement code

### 6.1 Reviewed glossary expansion

Glossary entries are constrained by country, language, reviewed triggers, and a query limit. A glossary term helps find evidence; it does not become evidence itself.

Source: `app/retrieval/glossary.py`

```python
def glossary_queries(
    message: str,
    country: str,
    language: str,
    *,
    enabled: bool | None = None,
) -> list[str]:
    glossary_enabled = (
        settings.OPENSEARCH_GLOSSARY_ENABLED
        if enabled is None
        else enabled
    )
    if not glossary_enabled:
        return []

    queries: list[str] = []
    for entry in load_glossary(settings.OPENSEARCH_GLOSSARY_PATH):
        if not locale_applies(entry, country, language):
            continue
        if not any(
            _matches_trigger(message, str(trigger))
            for trigger in entry.get("triggers", [])
        ):
            continue
        for query in entry.get("queries", []):
            if query not in queries:
                queries.append(query)
            if len(queries) >= settings.OPENSEARCH_GLOSSARY_QUERY_LIMIT:
                return queries
    return queries
```

The actual implementation performs the locale checks inline. The abbreviated `locale_applies` name above represents those checks for readability.

### 6.2 Reciprocal-rank fusion

RRF combines the order from lexical and semantic search without letting the raw score scale of one system dominate the other.

Source: `app/retrieval/experiments.py`

```python
def reciprocal_rank_fusion(
    rankings: Sequence[Iterable[Hashable]],
    *,
    k: int = 60,
) -> dict[Hashable, float]:
    denominator = max(1, int(k))
    scores: dict[Hashable, float] = defaultdict(float)
    for ranking in rankings:
        seen: set[Hashable] = set()
        for position, key in enumerate(ranking, start=1):
            if key in seen:
                continue
            seen.add(key)
            scores[key] += 1.0 / (denominator + position)
    return dict(scores)
```

Integration point in `OpenSearchSectionProvider._merge_hits`:

```python
if self.experimental_features and settings.RETRIEVAL_VNEXT_RRF_ENABLED:
    text_ranking = self._ranked_hit_ids(text_hits)
    vector_ranking = self._ranked_hit_ids(vector_hits)
    fused = reciprocal_rank_fusion(
        [text_ranking, vector_ranking],
        k=settings.RETRIEVAL_RRF_K,
    )
```

### 6.3 Bedrock reranking

The reranker receives a bounded candidate set with document metadata and content. If Bedrock fails or returns an invalid response, the original ordering is retained.

Source: `app/retrieval/bedrock_reranker.py`

```python
def rerank_rows(
    query: str,
    rows: list[tuple[dict[str, Any], float]],
    *,
    correlation_id: str,
) -> list[tuple[dict[str, Any], float]]:
    candidates = rows[
        : settings.RETRIEVAL_VNEXT_RERANK_CANDIDATE_COUNT
    ]
    sources = [
        {
            "type": "INLINE",
            "inlineDocumentSource": {
                "type": "TEXT",
                "textDocument": {"text": _candidate_text(row)},
            },
        }
        for row, _score in candidates
    ]

    try:
        response = get_aws_clients().bedrock_agent_runtime.rerank(
            queries=[
                {"type": "TEXT", "textQuery": {"text": query}}
            ],
            sources=sources,
            rerankingConfiguration={
                "type": "BEDROCK_RERANKING_MODEL",
                "bedrockRerankingConfiguration": {
                    "modelConfiguration": {
                        "modelArn": (
                            settings.RETRIEVAL_VNEXT_RERANK_MODEL_ARN
                        )
                    },
                    "numberOfResults": (
                        settings.RETRIEVAL_VNEXT_RERANK_RESULT_COUNT
                    ),
                },
            },
        )
    except (BotoCoreError, ClientError, KeyError, TypeError, ValueError):
        return rows

    return apply_rerank_response_without_dropping_remaining_rows(
        response,
        candidates,
        rows,
    )
```

The final helper call above summarizes the implementation's response validation, de-duplication, and append-remaining behavior.

### 6.4 Parent-section diversity

This prevents several fragments from one long policy section from occupying every evidence slot.

Source: `app/retrieval/experiments.py`

```python
def diversify_by_parent(
    documents: Sequence[dict[str, Any]],
    *,
    max_results: int,
    max_per_parent: int = 1,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    counts: dict[str, int] = defaultdict(int)
    for document in documents:
        metadata = document.get("metadata", {})
        parent = str(
            metadata.get("parent_section_id")
            or metadata.get("section_id")
            or document.get("id", "")
        )
        if counts[parent] >= max_per_parent:
            continue
        result.append(document)
        counts[parent] += 1
        if len(result) >= max_results:
            break
    return result
```

### 6.5 Neighbor expansion

After selecting strong parent sections, vNext may append a bounded number of sibling chunks from the same source and parent. This helps recover nearby conditions, exceptions, and definitions.

Source: `app/retrieval/opensearch_sections.py`

```python
def _expand_neighbor_rows(
    self,
    client: OpenSearch,
    rows: list[tuple[dict[str, Any], float]],
    country: str,
    language: str,
    correlation_id: str,
) -> list[tuple[dict[str, Any], float]]:
    limit = max(0, int(settings.RETRIEVAL_NEIGHBOR_LIMIT))
    if not (
        rows
        and limit
        and self.experimental_features
        and settings.RETRIEVAL_VNEXT_NEIGHBOR_EXPANSION_ENABLED
    ):
        return rows

    selected = rows[: max(1, self.result_count - limit)]
    neighbors = fetch_same_parent_neighbors(
        client=client,
        selected=selected,
        country=country,
        language=language,
        limit=limit,
    )
    return [*selected, *neighbors][: self.result_count]
```

`fetch_same_parent_neighbors` above represents the implementation's inline, locale-filtered OpenSearch loop. It is shown this way to keep the reference focused.

### 6.6 Evidence selector

The evidence selector does not answer the question. It chooses the most directly relevant approved sections from a bounded candidate list. Failure falls back to the existing ranking.

Source: `app/retrieval/opensearch_sections.py`

```python
def _select_evidence_rows(
    self,
    message: str,
    rows: list[tuple[dict[str, Any], float]],
    correlation_id: str,
) -> list[tuple[dict[str, Any], float]]:
    selector_enabled = (
        settings.OPENSEARCH_EVIDENCE_SELECTOR_ENABLED
        if self.evidence_selector_enabled is None
        else self.evidence_selector_enabled
    )
    if not selector_enabled or not rows:
        return rows

    candidates = _selector_candidates(
        rows,
        settings.OPENSEARCH_EVIDENCE_SELECTOR_CANDIDATE_COUNT,
    )
    response = get_aws_clients().bedrock_runtime.converse(
        modelId=settings.BEDROCK_MODEL_ARN,
        system=[{"text": EVIDENCE_SELECTION_INSTRUCTIONS}],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "text": format_question_and_candidates(
                            message,
                            candidates,
                        )
                    }
                ],
            }
        ],
        inferenceConfig={
            "maxTokens": (
                settings.OPENSEARCH_EVIDENCE_SELECTOR_MAX_OUTPUT_TOKENS
            )
        },
    )
    return apply_valid_selected_ranks_or_original_rows(
        response,
        candidates,
        rows,
    )
```

The named formatting/constants at the end of this excerpt summarize inline implementation code. The production source contains the full prompt, JSON parsing, validation, logging, and fallback logic.

### 6.7 Evidence contract and numeric validation

The vNext answer evaluator retries malformed evidence-contract output once, safely abstains when evidence is insufficient, and flags unsupported measurable claims.

Source: `scripts/evaluate_interaction_history.py` and `app/retrieval/vnext_quality.py`

```python
for attempts in range(1, 3):
    model_response = model_router.generate(
        package,
        retrieval_result,
        correlation_id,
    )
    contract = parse_vnext_evidence_contract(
        model_response.text,
        retrieval_result.documents,
    )
    if contract.valid or contract.reason == "answer_not_approved":
        break

if not contract.valid:
    return {
        "status": (
            "SAFE_ABSTENTION"
            if contract.reason == "answer_not_approved"
            else "EVIDENCE_CONTRACT_REJECTED"
        ),
        "answer": "",
    }

unsupported = vnext_unsupported_numeric_claims(
    contract.answer,
    question,
    retrieval_result.documents,
    contract.evidence_ids,
)

return {
    "status": (
        "APPROVED"
        if not unsupported
        else "NUMERIC_REVIEW_REQUIRED"
    ),
    "answer": contract.answer,
    "evidence_ids": list(contract.evidence_ids),
}
```

## 7. Full vNext evaluation profile

The full profile enables experimental switches only inside the evaluator process.

Source: `scripts/evaluate_interaction_history.py`

```python
def _configure_full_vnext_profile() -> None:
    settings.RETRIEVAL_VNEXT_GLOSSARY_ENABLED = True
    settings.RETRIEVAL_VNEXT_EVIDENCE_SELECTOR_ENABLED = True
    settings.RETRIEVAL_VNEXT_RRF_ENABLED = True
    settings.RETRIEVAL_VNEXT_PARENT_DIVERSITY_ENABLED = True
    settings.RETRIEVAL_VNEXT_NEIGHBOR_EXPANSION_ENABLED = True
```

Bedrock reranking is enabled only when both the flag and model ARN are configured.

```python
rerank_enabled = bool(
    profile == "full"
    and settings.RETRIEVAL_VNEXT_RERANK_ENABLED
    and settings.RETRIEVAL_VNEXT_RERANK_MODEL_ARN
)
```

## 8. Safe default configuration

Source: `config/settings.py`

```text
RETRIEVAL_PROVIDER=opensearch_section
OPENSEARCH_INDEX=askvera-policy-sections

RETRIEVAL_SHADOW_ENABLED=false
RETRIEVAL_SHADOW_SAMPLE_RATE=0.0
RETRIEVAL_VNEXT_PROVIDER=opensearch_section
RETRIEVAL_VNEXT_PIPELINE_VERSION=disabled
OPENSEARCH_VNEXT_INDEX=

RETRIEVAL_VNEXT_RESULT_COUNT=8
RETRIEVAL_VNEXT_GLOSSARY_ENABLED=false
RETRIEVAL_VNEXT_EVIDENCE_SELECTOR_ENABLED=false
RETRIEVAL_VNEXT_RRF_ENABLED=false
RETRIEVAL_VNEXT_PARENT_DIVERSITY_ENABLED=false
RETRIEVAL_VNEXT_NEIGHBOR_EXPANSION_ENABLED=false
RETRIEVAL_VNEXT_RERANK_ENABLED=false
```

These defaults mean a normal deployment continues to use the current path only.

## 9. Benchmark result recorded during this work

Completed rated historical benchmark: 76 questions.

| Metric | Current | vNext |
|---|---:|---:|
| Questions evaluated | 76 | 76 |
| Questions with retrieved evidence | 69 | 69 |
| Questions without retrieved evidence | 7 | 7 |
| Document result rate across all interactions | 90.79% | 90.79% |
| Retrieval-required cases | 69 | 69 |
| Retrieval-required cases with evidence | 69 | 69 |
| Retrieval-required coverage | 100% | 100% |
| Intentionally routed without retrieval | 7 | 7 |
| Grounded approved answers | Not measured in this historical run | 57 |
| Safe abstentions | Not measured in this historical run | 11 |
| Routed assistant-meta questions | Not applicable to retrieval recall | 3 |
| Routed off-topic questions | Not applicable to retrieval recall | 4 |
| Numeric-review-required answers | Not measured in this historical run | 1 |

The seven no-document interactions are the same in both pipelines. All seven
were intentionally routed as assistant-meta or off-topic requests; none was a
knowledge retrieval attempt. Therefore, `90.79%` is an all-interaction document
result rate, not retrieval recall.

This historical pilot has an answer-validation asymmetry: only vNext answers
were generated under the evidence contract. The evaluator now generates both
`current_answer` and `vnext_answer` through the same prompt builder, evidence
contract, retry policy, and citation-aware numeric validator. Promotion must use
a new parity run, not the asymmetric answer counts above.

Interpretation:

- Both pipelines returned some evidence for every retrieval-required case in
  this rated set. This does not establish that the evidence was correct.
- Expected-section recall cannot be calculated until the knowledge cases have
  reviewed expected-source or expected-section labels.
- vNext has demonstrated stronger ranking controls, terminology support, evidence enforcement, numeric validation, and safe abstention behavior.
- The full historical evaluation must finish, and low-confidence or failed cases must receive human review, before promotion.

## 10. Evaluation command

```powershell
python scripts/evaluate_interaction_history.py `
  --input <interaction-history.md> `
  --pipeline both `
  --vnext-profile full `
  --load-ssm `
  --generate-answers `
  --output-dir outputs/interaction_quality `
  --run-name interaction-vnext-evaluation
```

The evaluator checkpoints after each question and resumes by default. It does not write chat analytics, cache entries, or user-visible answers.

For retrieval-only ablation, omit `--generate-answers` and run each named
profile with a unique run name: `index-only`, `glossary`, `rrf`,
`parent-diversity`, `neighbor-expansion`, `evidence-selector`, `rerank`, and
`full`. The `rerank` profile refuses to run unless its model is configured, so
an unconfigured experiment cannot be mistaken for a valid rerank result.

## 11. Source map

| Responsibility | Source file |
|---|---|
| Primary/shadow orchestration | `app/retrieval/service.py` |
| Shared OpenSearch retrieval | `app/retrieval/opensearch_sections.py` |
| Query planning and local reranking helpers | `app/retrieval/providers.py` |
| RRF and parent diversity helpers | `app/retrieval/experiments.py` |
| Optional Bedrock reranker | `app/retrieval/bedrock_reranker.py` |
| Reviewed query glossary | `app/retrieval/glossary.py` |
| Glossary data | `config/search_glossary.json` |
| Evidence/numeric validation improvements | `app/retrieval/vnext_quality.py` |
| Historical evaluator | `scripts/evaluate_interaction_history.py` |
| Runtime settings | `config/settings.py` |
| Shadow rollout procedure | `docs/RETRIEVAL_VNEXT_SHADOW_ROLLOUT.md` |

## 12. Promotion rule

Do not promote vNext merely because it produces more answers. Promote only when reviewed evaluation confirms that it preserves or improves:

1. expected-section recall;
2. factual answer completeness;
3. citation correctness;
4. country and language isolation;
5. global-document scope;
6. numeric grounding;
7. p50 and p95 latency;
8. error and throttling rates; and
9. cost per answered question.

Promotion should be one reversible configuration change. The current index and current provider configuration remain the rollback target.
