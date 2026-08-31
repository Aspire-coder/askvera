"""Unit tests for retrieval normalization."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.retrieval import service as retrieval_service_module
from app.retrieval import providers as retrieval_providers
from app.retrieval import BedrockRetrievalProvider, RetrievedDocument, RetrievalResult, RetrievalService
from app.retrieval.providers import (
    _expanded_retrieval_query,
    _tokens,
    _planned_retrieval_plan,
    _planned_retrieval_queries,
    _parse_planned_query_plan,
    _reference_score,
    _retrieval_configuration,
    _retrieval_queries,
    _rerank_documents,
    confidence_from_sources,
)
from config import settings


@pytest.fixture(autouse=True)
def disable_shadow_analytics(monkeypatch):
    """Retrieval unit tests must not connect to operational analytics storage."""
    monkeypatch.setattr(retrieval_service_module, "record_retrieval_shadow_comparison", MagicMock())
    monkeypatch.setattr(
        retrieval_service_module,
        "get_retrieval_runtime_control",
        lambda: SimpleNamespace(
            mode="shadow" if settings.RETRIEVAL_SHADOW_ENABLED else "current",
            sample_rate=settings.RETRIEVAL_SHADOW_SAMPLE_RATE,
        ),
    )


def test_retrieval_plan_adds_reviewed_spaced_variant_for_joined_business_term(monkeypatch) -> None:
    """Joined policy terms get an extra approved query without enabling glossary expansion."""
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_ENABLED", False)
    monkeypatch.setattr(retrieval_providers.settings, "OPENSEARCH_GLOSSARY_ENABLED", False)

    plan = _planned_retrieval_plan(
        "How can I become a recognizedmanager?",
        "US",
        "en",
        "joined-term-cid",
    )

    assert plan.queries[0] == "How can I become a recognizedmanager?"
    assert "recognized manager" in plan.queries


class _StaticProvider:
    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name

    def retrieve(self, message: str, country: str, language: str, role: str, correlation_id: str) -> RetrievalResult:
        return RetrievalResult(
            documents=[],
            citations=[],
            confidence=1.0,
            metadata={"provider": self.provider_name},
        )


class _RecordingProvider:
    def __init__(self, provider_name: str, document_id: str, *, fail: bool = False) -> None:
        self.provider_name = provider_name
        self.document_id = document_id
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def retrieve(self, message: str, country: str, language: str, role: str, correlation_id: str) -> RetrievalResult:
        self.calls.append((message, correlation_id))
        if self.fail:
            raise RuntimeError("shadow failed")
        document = RetrievedDocument(
            id=self.document_id,
            title=f"{self.document_id}.pdf",
            content="approved content",
            source=f"s3://kb/{self.document_id}.pdf",
            score=0.8,
        )
        return RetrievalResult(
            documents=[document],
            citations=[document.to_source()],
            confidence=0.8,
            metadata={"provider": self.provider_name},
        )


def test_retrieval_service_refreshes_provider_after_config_load(monkeypatch) -> None:
    """The singleton must pick up SSM-loaded retrieval config after import time."""
    monkeypatch.setattr(settings, "RETRIEVAL_PROVIDER", "bedrock")
    service = RetrievalService()
    monkeypatch.setattr(service, "_default_provider", lambda: _StaticProvider(settings.RETRIEVAL_PROVIDER))

    monkeypatch.setattr(settings, "RETRIEVAL_PROVIDER", "opensearch_section")

    result = service.retrieve("question", "CA", "en", "new_prospect", "cid")

    assert result.metadata["provider"] == "opensearch_section"


def test_shadow_retrieval_is_inert_by_default(monkeypatch) -> None:
    primary = _RecordingProvider("primary", "primary-document")
    shadow = _RecordingProvider("shadow", "shadow-document")
    service = RetrievalService(provider=primary, shadow_provider=shadow)
    monkeypatch.setattr(settings, "RETRIEVAL_SHADOW_ENABLED", False)
    monkeypatch.setattr(
        retrieval_service_module,
        "_submit_shadow_task",
        lambda task: (_ for _ in ()).throw(AssertionError("shadow task must not run")),
    )

    result = service.retrieve("question", "CA", "en", "new_prospect", "cid")

    assert result.documents[0].id == "primary-document"
    assert shadow.calls == []


def test_runtime_current_mode_suppresses_configured_shadow(monkeypatch) -> None:
    primary = _RecordingProvider("primary", "primary-document")
    shadow = _RecordingProvider("shadow", "shadow-document")
    service = RetrievalService(provider=primary, shadow_provider=shadow)
    monkeypatch.setattr(settings, "RETRIEVAL_SHADOW_ENABLED", True)
    monkeypatch.setattr(settings, "RETRIEVAL_SHADOW_SAMPLE_RATE", 1.0)
    monkeypatch.setattr(
        retrieval_service_module,
        "get_retrieval_runtime_control",
        lambda: SimpleNamespace(mode="current", sample_rate=0.0),
    )

    result = service.retrieve("question", "CA", "en", "new_prospect", "cid")

    assert result.documents[0].id == "primary-document"
    assert shadow.calls == []


def test_shadow_retrieval_never_replaces_primary_result(monkeypatch) -> None:
    primary = _RecordingProvider("primary", "primary-document")
    shadow = _RecordingProvider("shadow", "shadow-document")
    service = RetrievalService(provider=primary, shadow_provider=shadow)
    monkeypatch.setattr(settings, "RETRIEVAL_SHADOW_ENABLED", True)
    monkeypatch.setattr(settings, "RETRIEVAL_SHADOW_SAMPLE_RATE", 1.0)
    monkeypatch.setattr(settings, "RETRIEVAL_VNEXT_PROVIDER", "opensearch_section")
    monkeypatch.setattr(settings, "OPENSEARCH_INDEX", "uat-index")
    monkeypatch.setattr(settings, "OPENSEARCH_VNEXT_INDEX", "vnext-index")
    monkeypatch.setattr(retrieval_service_module, "_submit_shadow_task", lambda task: task())

    result = service.retrieve("question", "CA", "en", "new_prospect", "cid")

    assert result.documents[0].id == "primary-document"
    assert shadow.calls == [("question", "cid-shadow")]
    comparison = retrieval_service_module.record_retrieval_shadow_comparison.call_args.args[0]
    assert comparison["primary_top_id"] == "primary-document"
    assert comparison["vnext_top_id"] == "shadow-document"
    assert comparison["top_result_matches"] is False
    assert "message" not in comparison


def test_shadow_failure_cannot_fail_primary_retrieval(monkeypatch) -> None:
    primary = _RecordingProvider("primary", "primary-document")
    shadow = _RecordingProvider("shadow", "shadow-document", fail=True)
    service = RetrievalService(provider=primary, shadow_provider=shadow)
    monkeypatch.setattr(settings, "RETRIEVAL_SHADOW_ENABLED", True)
    monkeypatch.setattr(settings, "RETRIEVAL_SHADOW_SAMPLE_RATE", 1.0)
    monkeypatch.setattr(settings, "RETRIEVAL_VNEXT_PROVIDER", "opensearch_section")
    monkeypatch.setattr(settings, "OPENSEARCH_INDEX", "uat-index")
    monkeypatch.setattr(settings, "OPENSEARCH_VNEXT_INDEX", "vnext-index")
    monkeypatch.setattr(retrieval_service_module, "_submit_shadow_task", lambda task: task())

    result = service.retrieve("question", "CA", "en", "new_prospect", "cid")

    assert result.documents[0].id == "primary-document"
    assert shadow.calls == [("question", "cid-shadow")]


def test_shadow_orchestration_failure_cannot_fail_primary_retrieval(monkeypatch) -> None:
    primary = _RecordingProvider("primary", "primary-document")
    service = RetrievalService(provider=primary)
    monkeypatch.setattr(
        service,
        "_submit_shadow_comparison",
        lambda **_: (_ for _ in ()).throw(RuntimeError("shadow orchestration failed")),
    )

    result = service.retrieve("question", "CA", "en", "new_prospect", "cid")

    assert result.documents[0].id == "primary-document"
    assert primary.calls == [("question", "cid")]


def test_reranking_flag_is_applied_only_to_the_shadow_provider(monkeypatch) -> None:
    created: list[tuple[str, str | None, bool]] = []

    def recording_factory(
        provider_name,
        *,
        index_name=None,
        enable_bedrock_rerank=False,
        **kwargs,
    ):
        created.append((provider_name, index_name, enable_bedrock_rerank))
        if index_name == "vnext-index":
            assert kwargs == {
                "enable_rrf": settings.RETRIEVAL_VNEXT_RRF_ENABLED,
                "enable_parent_diversity": settings.RETRIEVAL_VNEXT_PARENT_DIVERSITY_ENABLED,
                "enable_authority_ranking": settings.RETRIEVAL_VNEXT_AUTHORITY_RANKING_ENABLED,
                "enable_parent_child": settings.RETRIEVAL_VNEXT_PARENT_CHILD_ENABLED,
                "enable_signal_confidence": settings.RETRIEVAL_VNEXT_SIGNAL_CONFIDENCE_ENABLED,
                "enable_evidence_selector": settings.RETRIEVAL_VNEXT_EVIDENCE_SELECTOR_ENABLED,
                "enable_retrieval_hardening": settings.RETRIEVAL_VNEXT_HARDENING_ENABLED,
                "profile_name": "vnext",
            }
        return _RecordingProvider(provider_name, f"document-{len(created)}")

    monkeypatch.setattr(RetrievalService, "_provider_for_name", staticmethod(recording_factory))
    monkeypatch.setattr(settings, "RETRIEVAL_PROVIDER", "opensearch_section")
    monkeypatch.setattr(settings, "RETRIEVAL_SHADOW_ENABLED", True)
    monkeypatch.setattr(settings, "RETRIEVAL_SHADOW_SAMPLE_RATE", 1.0)
    monkeypatch.setattr(settings, "RETRIEVAL_VNEXT_PROVIDER", "opensearch_section")
    monkeypatch.setattr(settings, "OPENSEARCH_INDEX", "uat-index")
    monkeypatch.setattr(settings, "OPENSEARCH_VNEXT_INDEX", "vnext-index")
    monkeypatch.setattr(settings, "RETRIEVAL_VNEXT_RERANK_ENABLED", True)
    monkeypatch.setattr(retrieval_service_module, "_submit_shadow_task", lambda task: task())

    service = RetrievalService()
    service.retrieve("question", "CA", "en", "new_prospect", "cid")

    assert created[0] == ("opensearch_section", None, False)
    assert created[1] == ("opensearch_section", "vnext-index", True)


def test_provider_result_extracts_api_sources() -> None:
    """Retrieved documents are normalized into API-compatible sources."""
    provider = BedrockRetrievalProvider()
    result = provider._result(
        [
            RetrievedDocument(
                id="doc",
                title="doc.pdf",
                content="approved excerpt",
                source="s3://kb/doc.pdf",
                excerpt="approved excerpt",
                page="3",
                document_version="v1",
                country="US",
                language="en",
                score=0.82,
            )
        ]
    )

    assert result.confidence == 0.82
    assert result.sources[0]["uri"] == "s3://kb/doc.pdf"
    assert result.sources[0]["page"] == "3"
    assert result.sources[0]["documentVersion"] == "v1"


def test_confidence_falls_back_to_citation_quality() -> None:
    """Confidence remains useful when Bedrock omits explicit scores."""
    confidence = confidence_from_sources(
        [
            {"uri": "s3://kb/one.pdf", "excerpt": "one"},
            {"uri": "s3://kb/two.pdf", "excerpt": "two"},
        ]
    )

    assert confidence > 0.65


def test_retrieval_rerank_prefers_exact_question_terms() -> None:
    """Local reranking should prefer candidate chunks that match the user's item."""
    documents = [
        RetrievedDocument(
            id="manager",
            title="CA-EN-Company-Policy.pdf",
            content="Manager is achieved by generating 120 Open Group Case Credits.",
            source="s3://kb/policy.pdf",
            score=0.91,
        ),
        RetrievedDocument(
            id="assistant-manager",
            title="CA-EN-Company-Policy.pdf",
            content="Assistant Manager is achieved by generating 75 Open Group Case Credits.",
            source="s3://kb/policy.pdf",
            score=0.86,
        ),
    ]

    reranked = _rerank_documents("How do I qualify as Assistant Manager?", documents)

    assert reranked[0].id == "assistant-manager"


def test_retrieval_rerank_prefers_direct_requirement_over_related_opt_in_text() -> None:
    """A direct rank requirement should outrank related but different qualification text."""
    documents = [
        RetrievedDocument(
            id="preferred-customer-opt-in",
            title="CA-EN-Company-Policy.pdf",
            content=(
                "When the Preferred Customer generates 2CC within any 2-consecutive-Month period, "
                "he/she is entitled to a Discount and can Opt-in to the Marketing Plan as an FBO "
                "at the Assistant Supervisor level."
            ),
            source="s3://kb/policy.pdf",
            score=0.91,
        ),
        RetrievedDocument(
            id="assistant-supervisor-requirement",
            title="CA-EN-Company-Policy.pdf",
            content=(
                "An FBO reaches the level of Assistant Supervisor by generating a total of "
                "2 Open Group Case Credits in any single Operating Company within any "
                "2 consecutive Months."
            ),
            source="s3://kb/policy.pdf",
            score=0.72,
        ),
    ]

    reranked = _rerank_documents("How many Case Credits do I need to become Assistant Supervisor?", documents)

    assert reranked[0].id == "assistant-supervisor-requirement"


def test_retrieval_rerank_understands_lowercase_bonus_phrase() -> None:
    """Lowercase business phrases should still anchor retrieval to the right chunk."""
    documents = [
        RetrievedDocument(
            id="leadership-bonus",
            title="CA-EN-Company-Policy.pdf",
            content="Leadership Bonus is paid to qualified Managers on qualifying sales.",
            source="s3://kb/policy.pdf",
            score=0.88,
        ),
        RetrievedDocument(
            id="personal-retail-bonus",
            title="CA-EN-Company-Policy.pdf",
            content="Personal Retail Bonus is the difference between Suggested Retail Price and wholesale cost.",
            source="s3://kb/policy.pdf",
            score=0.74,
        ),
    ]

    reranked = _rerank_documents("what is the personal retail bonus %?", documents)

    assert reranked[0].id == "personal-retail-bonus"


def test_retrieval_rerank_uses_single_word_rank_anchor() -> None:
    """Single-word rank names such as Supervisor should still anchor retrieval."""
    documents = [
        RetrievedDocument(
            id="assistant-supervisor",
            title="CA-EN-Company-Policy.pdf",
            content=(
                "Assistant Supervisor is achieved by generating a total of "
                "2 Open Group Case Credits within any 2 consecutive Months."
            ),
            source="s3://kb/policy.pdf",
            score=0.91,
        ),
        RetrievedDocument(
            id="supervisor",
            title="CA-EN-Company-Policy.pdf",
            content=(
                "Supervisor is achieved by generating a total of "
                "10 Open Group Case Credits within any Month."
            ),
            source="s3://kb/policy.pdf",
            score=0.74,
        ),
    ]

    reranked = _rerank_documents("What are the Case Credits requirements to become a Supervisor?", documents)

    assert reranked[0].id == "supervisor"


def test_retrieval_rerank_prefers_multiword_rank_requirement() -> None:
    """Multi-word ranks must not inherit neighboring Manager requirements."""
    documents = [
        RetrievedDocument(
            id="manager",
            title="CA-EN-Company-Policy.pdf",
            content=(
                "Manager is achieved by generating a total of "
                "120 Open Group Case Credits within 1-2 consecutive Months, "
                "or 150 Open Group Case Credits within 3-4 consecutive Months."
            ),
            source="s3://kb/policy.pdf",
            score=0.94,
        ),
        RetrievedDocument(
            id="assistant-manager",
            title="CA-EN-Company-Policy.pdf",
            content=(
                "Assistant Manager is achieved by generating a total of "
                "75 Open Group Case Credits within any Month."
            ),
            source="s3://kb/policy.pdf",
            score=0.68,
        ),
    ]

    reranked = _rerank_documents("How do I qualify as Assistant Manager?", documents)

    assert reranked[0].id == "assistant-manager"


def test_retrieval_rerank_uses_bedrock_score_as_tiebreaker() -> None:
    """When local text is equally relevant, the provider score should still matter."""
    documents = [
        RetrievedDocument(
            id="low-score",
            title="CA-EN-Company-Policy.pdf",
            content="Supervisor is achieved by generating 10 Open Group Case Credits within any Month.",
            source="s3://kb/policy.pdf",
            score=0.42,
        ),
        RetrievedDocument(
            id="high-score",
            title="CA-EN-Company-Policy.pdf",
            content="Supervisor is achieved by generating 10 Open Group Case Credits within any Month.",
            source="s3://kb/policy.pdf",
            score=0.88,
        ),
    ]

    reranked = _rerank_documents("What are the Case Credits requirements to become a Supervisor?", documents)

    assert reranked[0].id == "high-score"


def test_reference_score_reads_bedrock_retrieve_score_shapes() -> None:
    """Bedrock Retrieve scores should survive normalization for confidence/reranking."""
    assert _reference_score({"score": 0.74}) == 0.74
    assert _reference_score({"retrievalScore": 74}) == 0.74
    assert _reference_score({"metadata": {"retrieval_score": "0.63"}}) == 0.63


def test_bedrock_filter_accepts_old_and_new_country_metadata_keys() -> None:
    configuration = _retrieval_configuration(country="NL", language="nl", managed=False)
    filters = configuration["vectorSearchConfiguration"]["filter"]["andAll"]

    assert filters[0] == {
        "orAll": [
            {"equals": {"key": "country_code", "value": "NL"}},
            {"equals": {"key": "country", "value": "NL"}},
        ]
    }
    assert {"equals": {"key": "language", "value": "nl"}} in filters
    assert {"equals": {"key": "status", "value": "active"}} in filters


def test_provider_dedupe_keeps_different_chunks_with_same_prefix() -> None:
    """Chunk dedupe should not erase different sections that start similarly."""
    provider = BedrockRetrievalProvider()
    shared_prefix = "Company Policies and the Code of Professional Conduct. "
    documents = [
        RetrievedDocument(
            id="page-six",
            title="CA-EN-Company-Policy.pdf",
            content=shared_prefix + "Supervisor is achieved by generating 10 Open Group Case Credits.",
            source="s3://kb/policy.pdf",
            page="6",
            score=0.8,
        ),
        RetrievedDocument(
            id="page-six-manager",
            title="CA-EN-Company-Policy.pdf",
            content=shared_prefix + "Manager is achieved by generating 120 Open Group Case Credits.",
            source="s3://kb/policy.pdf",
            page="6",
            score=0.7,
        ),
    ]

    deduped = provider._dedupe_documents(documents)

    assert {document.id for document in deduped} == {"page-six", "page-six-manager"}


def test_retrieval_query_expands_case_credit_rank_terms() -> None:
    """Case Credit rank questions should include policy-style retrieval wording."""
    query = _expanded_retrieval_query("What are the Case Credits requirements to become a Supervisor?")
    queries = _retrieval_queries("What are the Case Credits requirements to become a Supervisor?")

    assert "Supervisor?" in query
    assert "supervisor is achieved by generating open group case credits" in query
    assert queries[0] == "What are the Case Credits requirements to become a Supervisor?"
    assert "supervisor is achieved by generating open group case credits" in queries


def test_hardened_query_expands_generic_manager_qualification(monkeypatch) -> None:
    monkeypatch.setattr(
        retrieval_providers.settings,
        "OPENSEARCH_RETRIEVAL_HARDENING_ENABLED",
        True,
    )

    queries = _retrieval_queries(
        "What does the company policy say about manager qualifications?"
    )

    assert "manager is achieved by generating" in queries


def test_hardened_query_expands_purchase_channel(monkeypatch) -> None:
    monkeypatch.setattr(
        retrieval_providers.settings,
        "OPENSEARCH_RETRIEVAL_HARDENING_ENABLED",
        True,
    )

    queries = _retrieval_queries(
        "Where can I buy Forever products in the United States?"
    )

    assert "selling products online personal Forever web shop approved FBO website" in queries


def test_retrieval_query_expands_bonus_terms() -> None:
    """Bonus questions should include the exact business phrase for retrieval."""
    query = _expanded_retrieval_query("What is the Personal Retail Bonus %?")
    queries = _retrieval_queries("What is the Personal Retail Bonus %?")

    assert "personal retail bonus" in query
    assert "personal retail bonus" in queries


def test_local_retrieval_tokens_preserve_multilingual_words_and_accents() -> None:
    """Local query heuristics must not drop non-English policy terminology."""
    tokens = _tokens("Quelles sont les conditions d'inactivité du FBO? Где офис?")

    assert "conditions" in tokens
    assert "inactivite" in tokens
    assert "fbo" in tokens
    assert "где" in tokens
    assert "офис" in tokens


def test_multilingual_policy_query_keeps_terms_for_local_expansion() -> None:
    """Accented policy questions should produce focused, non-empty expansions."""
    queries = _retrieval_queries("Quelles sont les conditions d'inactivité du Manager?")

    assert queries[0] == "Quelles sont les conditions d'inactivité du Manager?"
    assert any("manager" in query for query in queries)


def test_multilingual_query_planner_uses_runtime_question_without_country_aliases(monkeypatch) -> None:
    """Any market/language can create search phrases from the live question."""
    runtime = MagicMock()
    runtime.converse.return_value = {
        "output": {
            "message": {
                "content": [
                    {
                        "text": '{"queries":["voorwaarden supervisor case credits","supervisor case credit requirements"]}'
                    }
                ]
            }
        }
    }
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_ENABLED", True)
    monkeypatch.setattr(
        retrieval_providers,
        "get_aws_clients",
        lambda: SimpleNamespace(bedrock_runtime=runtime),
    )

    queries = _planned_retrieval_queries(
        "Hoeveel CC zijn nodig om Supervisor te worden?",
        "NL",
        "nl",
        "cid",
    )

    assert queries[0] == "Hoeveel CC zijn nodig om Supervisor te worden?"
    assert "supervisor case credit requirements" in queries
    request_text = runtime.converse.call_args.kwargs["messages"][0]["content"][0]["text"]
    assert "Market: NL" in request_text
    assert "Requested language: nl" in request_text
    planner_prompt = runtime.converse.call_args.kwargs["system"][0]["text"]
    assert "requalification" in planner_prompt
    assert "inactivity" in planner_prompt
    assert "global_directory" in planner_prompt


def test_query_planner_schema_limits_untrusted_model_output(monkeypatch) -> None:
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_QUERY_COUNT", 2)
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_MAX_QUERY_CHARS", 20)
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_MAX_RESPONSE_CHARS", 2000)

    parsed = _parse_planned_query_plan(
        '{"queries":["first valid query","second query that is much too long","ignored",42],'
        '"document_scopes":["locale_policy","unknown"],"answer_shape":"unknown",'
        '"intent":"not_allowed","intent_confidence":4}'
    )

    assert parsed[0] == ["first valid query", "second query that is"]
    assert parsed[1] is False
    assert parsed[2] is False
    assert parsed[3] == "knowledge"
    assert parsed[5] == 1.0


def test_query_planner_parses_and_bounds_explicit_target_market(monkeypatch) -> None:
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_MAX_RESPONSE_CHARS", 2000)

    parsed = _parse_planned_query_plan(
        '{"queries":[],"document_scopes":["global_directory"],'
        '"target_market":"  United   Kingdom  "}'
    )

    assert parsed[7] == "United Kingdom"


def test_planner_target_market_must_be_grounded_in_user_text() -> None:
    assert retrieval_providers._grounded_target_market(
        "What is the minimum order in Antarctica?", "Antarctica"
    ) == "Antarctica"
    assert retrieval_providers._grounded_target_market(
        "What is the UK office number?", "United Kingdom"
    ) == "United Kingdom"
    assert retrieval_providers._grounded_target_market(
        "What is the Canada return policy?", "Antarctica"
    ) == ""


def test_planner_target_market_fallback_is_narrow_and_user_grounded() -> None:
    assert retrieval_providers._fallback_grounded_target_market(
        "What's the minimum order for becoming a manager in Antarctica?",
        ["minimum order Antarctica", "manager qualification Antarctica"],
    ) == "Antarctica"
    assert retrieval_providers._fallback_grounded_target_market(
        "How do I become a Manager?", ["manager qualification"]
    ) == ""
    assert retrieval_providers._fallback_grounded_target_market(
        "Tell me about working in Forever Living.", ["employment policy"]
    ) == ""
    assert retrieval_providers._fallback_grounded_target_market(
        "What's the minimum order for becoming a manager in Antarctica?", []
    ) == "Antarctica"
    assert retrieval_providers._fallback_grounded_target_market(
        "What's the minimum order for Antarctica?", []
    ) == "Antarctica"
    assert retrieval_providers._fallback_grounded_target_market(
        "What's the discount for Preferred Customer?", []
    ) == ""


def test_query_planner_rejects_invalid_container_types(monkeypatch) -> None:
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_MAX_RESPONSE_CHARS", 2000)

    with pytest.raises(ValueError, match="queries"):
        _parse_planned_query_plan('{"queries":"not-an-array"}')
    with pytest.raises(ValueError, match="document scopes"):
        _parse_planned_query_plan('{"queries":[],"document_scopes":"global_directory"}')


def test_query_planner_selects_document_scope_from_semantic_intent(monkeypatch) -> None:
    """Policy questions stay local while contact questions may use the global directory."""
    runtime = MagicMock()
    runtime.converse.side_effect = [
        {
            "output": {
                "message": {
                    "content": [
                        {
                            "text": '{"queries":["product classification policy"],'
                            '"document_scopes":["locale_policy"],'
                            '"answer_shape":"content"}'
                        }
                    ]
                }
            }
        },
        {
            "output": {
                "message": {
                    "content": [
                        {
                            "text": '{"queries":["Mexico office email"],'
                            '"document_scopes":["global_directory"]}'
                        }
                    ]
                }
            }
        },
        {
            "output": {
                "message": {
                    "content": [
                        {
                            "text": '{"queries":["Code of Conduct section"],'
                            '"document_scopes":["locale_policy"],'
                            '"answer_shape":"document_structure"}'
                        }
                    ]
                }
            }
        },
    ]
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_ENABLED", True)
    monkeypatch.setattr(
        retrieval_providers,
        "get_aws_clients",
        lambda: SimpleNamespace(bedrock_runtime=runtime),
    )

    policy_plan = _planned_retrieval_plan(
        "How are ingestible products classified in the policy?",
        "US",
        "en",
        "policy-cid",
    )
    directory_plan = _planned_retrieval_plan(
        "What is the Mexico office email address?",
        "CA",
        "en",
        "directory-cid",
    )
    structure_plan = _planned_retrieval_plan(
        "Which section contains the Code of Conduct?",
        "NO",
        "en",
        "structure-cid",
    )

    assert policy_plan.include_global_documents is False
    assert policy_plan.prefer_outline is False
    assert directory_plan.include_global_documents is True
    assert directory_plan.prefer_outline is False
    assert structure_plan.include_global_documents is False
    assert structure_plan.prefer_outline is True


def test_query_planner_routes_multilingual_explicit_handoff_as_client_action(monkeypatch) -> None:
    runtime = MagicMock()
    runtime.converse.side_effect = [
        {
            "output": {
                "message": {
                    "content": [{
                        "text": '{"queries":[],"document_scopes":[],"intent":"support_request",'
                        '"intent_confidence":0.99,"explicit_support_request":true}'
                    }]
                }
            }
        },
        {
            "output": {
                "message": {
                    "content": [{"text": '{"explicit_support_request":true}'}]
                }
            }
        },
    ]
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_ENABLED", True)
    monkeypatch.setattr(
        retrieval_providers,
        "get_aws_clients",
        lambda: SimpleNamespace(bedrock_runtime=runtime),
    )

    plan = _planned_retrieval_plan(
        "Je souhaite créer une demande auprès du service d'assistance.",
        "CA",
        "fr",
        "support-cid",
    )

    assert plan.client_action == "open_support_form"
    assert plan.conversation_intent == "support_request"
    assert runtime.converse.call_count == 2
    planner_prompt = runtime.converse.call_args_list[0].kwargs["system"][0]["text"]
    assert "user's language" in planner_prompt


def test_query_planner_routes_health_statement_without_opening_support(monkeypatch) -> None:
    runtime = MagicMock()
    runtime.converse.return_value = {
        "output": {
            "message": {
                "content": [{
                    "text": '{"queries":[],"document_scopes":[],"intent":"medical_claim",'
                    '"intent_confidence":0.98,"explicit_support_request":false}'
                }]
            }
        }
    }
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_ENABLED", True)
    monkeypatch.setattr(
        retrieval_providers,
        "get_aws_clients",
        lambda: SimpleNamespace(bedrock_runtime=runtime),
    )

    plan = _planned_retrieval_plan("I am having fever.", "US", "en", "medical-cid")

    assert plan.conversation_intent == "medical_claim"
    assert plan.client_action == ""
    assert runtime.converse.call_count == 1


def test_query_planner_cannot_misroute_return_policy_as_income_claim(monkeypatch) -> None:
    runtime = MagicMock()
    runtime.converse.side_effect = [
        {
            "output": {
                "message": {
                    "content": [{
                        "text": '{"queries":["return and refund policy"],'
                        '"document_scopes":["locale_policy"],"intent":"income_claim",'
                        '"intent_confidence":0.99,"explicit_support_request":false}'
                    }]
                }
            }
        },
        {"output": {"message": {"content": [{"text": '{"income_claim":false}'}]}}},
    ]
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_ENABLED", True)
    monkeypatch.setattr(
        retrieval_providers,
        "get_aws_clients",
        lambda: SimpleNamespace(bedrock_runtime=runtime),
    )

    plan = _planned_retrieval_plan("What is the return policy?", "US", "en", "returns-cid")

    assert plan.conversation_intent == "knowledge"
    assert plan.client_action == ""
    assert runtime.converse.call_count == 2


def test_query_planner_preserves_confirmed_income_claim(monkeypatch) -> None:
    runtime = MagicMock()
    runtime.converse.return_value = {
        "output": {
            "message": {
                "content": [{
                    "text": '{"queries":[],"document_scopes":[],"intent":"income_claim",'
                    '"intent_confidence":0.99,"explicit_support_request":false}'
                }]
            }
        }
    }
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_ENABLED", True)
    monkeypatch.setattr(
        retrieval_providers,
        "get_aws_clients",
        lambda: SimpleNamespace(bedrock_runtime=runtime),
    )

    plan = _planned_retrieval_plan("Can this replace my salary?", "US", "en", "income-cid")

    assert plan.conversation_intent == "income_claim"


def test_query_planner_routes_assistant_capability_without_document_search(monkeypatch) -> None:
    runtime = MagicMock()
    runtime.converse.return_value = {
        "output": {
            "message": {
                "content": [{
                    "text": '{"queries":[],"document_scopes":[],"intent":"assistant_meta",'
                    '"intent_subtype":"capability","intent_confidence":0.97,'
                    '"explicit_support_request":false}'
                }]
            }
        }
    }
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_ENABLED", True)
    monkeypatch.setattr(
        retrieval_providers,
        "get_aws_clients",
        lambda: SimpleNamespace(bedrock_runtime=runtime),
    )

    plan = _planned_retrieval_plan("What do you do?", "US", "en", "meta-cid")

    assert plan.conversation_intent == "assistant_meta"
    assert plan.conversation_subtype == "capability"
    assert plan.client_action == ""


def test_query_planner_rejects_broad_assistant_meta_for_unrelated_personal_question(monkeypatch) -> None:
    runtime = MagicMock()
    runtime.converse.return_value = {
        "output": {
            "message": {
                "content": [{
                    "text": '{"queries":[],"document_scopes":[],"intent":"assistant_meta",'
                    '"intent_subtype":"greeting","intent_confidence":0.98,'
                    '"explicit_support_request":false}'
                }]
            }
        }
    }
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_ENABLED", True)
    monkeypatch.setattr(
        retrieval_providers,
        "get_aws_clients",
        lambda: SimpleNamespace(bedrock_runtime=runtime),
    )

    plan = _planned_retrieval_plan("Who is your daddy?", "US", "en", "off-topic-cid")

    assert plan.conversation_intent == "off_topic"
    assert plan.conversation_subtype == ""


def test_query_planner_preserves_directory_lookup_when_assistant_meta_is_overbroad(monkeypatch) -> None:
    runtime = MagicMock()
    runtime.converse.return_value = {
        "output": {
            "message": {
                "content": [{
                    "text": '{"queries":["Dejan staff contact"],'
                    '"document_scopes":["global_directory"],"intent":"assistant_meta",'
                    '"intent_subtype":"capability","intent_confidence":0.98,'
                    '"explicit_support_request":false}'
                }]
            }
        }
    }
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_ENABLED", True)
    monkeypatch.setattr(
        retrieval_providers,
        "get_aws_clients",
        lambda: SimpleNamespace(bedrock_runtime=runtime),
    )

    plan = _planned_retrieval_plan("Who is Dejan?", "US", "en", "directory-cid")

    assert plan.conversation_intent == "knowledge"
    assert plan.include_global_documents is True
    assert plan.conversation_subtype == ""


def test_unverified_support_intent_fails_closed_to_knowledge(monkeypatch) -> None:
    runtime = MagicMock()
    runtime.converse.side_effect = [
        {
            "output": {
                "message": {
                    "content": [{
                        "text": '{"queries":["health statement"],"document_scopes":[],'
                        '"intent":"support_request","intent_confidence":0.99,'
                        '"explicit_support_request":true}'
                    }]
                }
            }
        },
        {
            "output": {
                "message": {
                    "content": [{"text": '{"explicit_support_request":false}'}]
                }
            }
        },
    ]
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_ENABLED", True)
    monkeypatch.setattr(
        retrieval_providers,
        "get_aws_clients",
        lambda: SimpleNamespace(bedrock_runtime=runtime),
    )

    plan = _planned_retrieval_plan("I am having fever.", "US", "en", "false-support-cid")

    assert plan.conversation_intent == "knowledge"
    assert plan.client_action == ""


def test_query_planner_always_includes_global_documents_for_sponsoring_questions(monkeypatch) -> None:
    runtime = MagicMock()
    runtime.converse.return_value = {
        "output": {
            "message": {
                "content": [{
                    "text": '{"queries":["international sponsoring Italy"],'
                    '"document_scopes":["locale_policy"],"intent":"knowledge",'
                    '"intent_confidence":0.99}'
                }]
            }
        }
    }
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_ENABLED", True)
    monkeypatch.setattr(
        retrieval_providers,
        "get_aws_clients",
        lambda: SimpleNamespace(bedrock_runtime=runtime),
    )

    plan = _planned_retrieval_plan("Who is the sponsor for Italy?", "IT", "en", "sponsor-cid")

    assert plan.include_global_documents is True


@pytest.mark.parametrize(
    ("question", "selected_market"),
    [
        ("What are the legal requirements in Baltics?", "US"),
        ("How can I become a member in Mexico?", "US"),
    ],
)
def test_query_planner_includes_global_documents_for_named_markets(
    monkeypatch,
    question: str,
    selected_market: str,
) -> None:
    """A named market opens global records even if the planner omits them."""
    runtime = MagicMock()
    runtime.converse.return_value = {
        "output": {
            "message": {
                "content": [{
                    "text": '{"queries":["market requirements"],'
                    '"document_scopes":["locale_policy"],"intent":"knowledge",'
                    '"intent_confidence":0.99}'
                }]
            }
        }
    }
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_ENABLED", True)
    monkeypatch.setattr(
        retrieval_providers,
        "get_aws_clients",
        lambda: SimpleNamespace(bedrock_runtime=runtime),
    )

    plan = _planned_retrieval_plan(question, selected_market, "en", "named-market-cid")

    assert plan.include_global_documents is True


def test_query_planner_includes_global_documents_for_unknown_directory_country(monkeypatch) -> None:
    """Operational directory intent must not depend on a configured widget market."""
    runtime = MagicMock()
    runtime.converse.return_value = {
        "output": {
            "message": {
                "content": [{
                    "text": '{"queries":["Thailand minimum order size"],'
                    '"document_scopes":["locale_policy"],"intent":"knowledge",'
                    '"intent_confidence":0.99}'
                }]
            }
        }
    }
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_ENABLED", True)
    monkeypatch.setattr(
        retrieval_providers,
        "get_aws_clients",
        lambda: SimpleNamespace(bedrock_runtime=runtime),
    )

    plan = _planned_retrieval_plan(
        "What is the minimum order size for Forever Thailand?",
        "US",
        "en",
        "unknown-directory-market-cid",
    )

    assert plan.include_global_documents is True


def test_operational_policy_question_does_not_open_global_scope_without_named_record(monkeypatch) -> None:
    """An operational phrase alone must not mix global records into local policy evidence."""
    runtime = MagicMock()
    runtime.converse.return_value = {
        "output": {
            "message": {
                "content": [{
                    "text": '{"queries":["United States accepted order payment methods"],'
                    '"document_scopes":["locale_policy"],"intent":"knowledge",'
                    '"intent_confidence":0.99}'
                }]
            }
        }
    }
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_ENABLED", True)
    monkeypatch.setattr(
        retrieval_providers,
        "get_aws_clients",
        lambda: SimpleNamespace(bedrock_runtime=runtime),
    )

    plan = _planned_retrieval_plan(
        "What payment methods are accepted for orders in the U.S.?",
        "US",
        "en",
        "local-payment-method-cid",
    )

    assert plan.include_global_documents is False
