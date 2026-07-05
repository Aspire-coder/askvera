"""Unit tests for the response pipeline."""

from app.models.responses import ModelResponse
from app.response import ResponseBuilder
from app.retrieval import RetrievedDocument, RetrievalResult


def test_response_builder_preserves_existing_api_shape() -> None:
    """ChatResponse converts back to the current widget payload."""
    retrieval_result = RetrievalResult(
        documents=[
            RetrievedDocument(
                id="doc",
                title="Policy",
                content="Policy content",
                source="s3://kb/policy.pdf",
                excerpt="Policy content",
                score=0.91,
            )
        ],
        citations=[],
        confidence=0.91,
    )
    model_response = ModelResponse(
        text="Answer",
        citations=retrieval_result.sources,
        confidence=0.91,
        provider="claude",
        model_name="model",
        latency_ms=123,
        metadata={"prompt_version": "v1"},
    )

    chat_response = ResponseBuilder().build(
        model_response=model_response,
        retrieval_result=retrieval_result,
        correlation_id="cid",
        session_metadata={"cache": "miss"},
    )

    assert chat_response.to_api_result() == {
        "response": "Answer",
        "sources": retrieval_result.sources,
        "confidence": 0.91,
        "correlationId": "cid",
    }
    assert chat_response.metadata["provider"] == "claude"
    assert chat_response.metadata["retrieved_document_count"] == 1
    assert chat_response.metadata["cache"] == "miss"
