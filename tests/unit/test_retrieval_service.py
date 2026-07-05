"""Unit tests for retrieval normalization."""

from app.retrieval import BedrockRetrievalProvider, RetrievedDocument
from app.retrieval.providers import confidence_from_sources


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
