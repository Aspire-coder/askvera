"""Unit tests for retrieval normalization."""

from app.retrieval import BedrockRetrievalProvider, RetrievedDocument, RetrievalResult, RetrievalService
from app.retrieval.providers import (
    _expanded_retrieval_query,
    _reference_score,
    _retrieval_queries,
    _rerank_documents,
    confidence_from_sources,
)
from config import settings


class _StaticProvider:
    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name

    def retrieve(self, message: str, country: str, language: str, role: str, correlation_id: str) -> RetrievalResult:
        return RetrievalResult(
            documents=[],
            confidence=1.0,
            sources=[],
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


def test_retrieval_query_expands_bonus_terms() -> None:
    """Bonus questions should include the exact business phrase for retrieval."""
    query = _expanded_retrieval_query("What is the Personal Retail Bonus %?")
    queries = _retrieval_queries("What is the Personal Retail Bonus %?")

    assert "personal retail bonus" in query
    assert "personal retail bonus" in queries
