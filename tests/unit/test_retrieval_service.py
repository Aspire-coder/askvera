"""Unit tests for retrieval normalization."""

from app.retrieval import BedrockRetrievalProvider, RetrievedDocument
from app.retrieval.providers import _rerank_documents, confidence_from_sources


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
