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
        text="Policy content",
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
        "response": "Policy content",
        "sources": retrieval_result.sources,
        "confidence": 0.91,
        "correlationId": "cid",
    }
    assert chat_response.metadata["provider"] == "claude"
    assert chat_response.metadata["retrieved_document_count"] == 1
    assert chat_response.metadata["cache"] == "miss"


def test_response_builder_prefers_answer_supporting_references() -> None:
    """References shown to users should be supporting evidence, not raw search dumps."""
    retrieval_result = RetrievalResult(
        documents=[
            RetrievedDocument(
                id="relevant",
                title="CA-EN-Company-Policy.pdf",
                content=(
                    "Assistant Supervisor is achieved by generating a total of "
                    "2 Open Group Case Credits in any single Operating Company "
                    "within any 2 consecutive Months."
                ),
                source="s3://kb/policy.pdf",
                excerpt="Assistant Supervisor is achieved by generating 2 Open Group Case Credits.",
                page="6",
                score=0.72,
            ),
            RetrievedDocument(
                id="noise",
                title="CA-EN-Company-Policy.pdf",
                content="Leadership Bonus requirements for unrelated incentives are listed in this section.",
                source="s3://kb/policy.pdf",
                excerpt="Leadership Bonus requirements for unrelated incentives.",
                page="26",
                score=0.9,
            ),
        ],
        citations=[],
        confidence=0.72,
    )
    model_response = ModelResponse(
        text="To become an Assistant Supervisor, you need 2 Open Group Case Credits within any 2 consecutive months.",
        citations=retrieval_result.sources,
        confidence=0.72,
        provider="claude",
        model_name="model",
    )

    chat_response = ResponseBuilder().build(
        model_response=model_response,
        retrieval_result=retrieval_result,
        correlation_id="cid",
    )

    assert chat_response.citations[0]["page"] == "6"
    assert "2 Open Group Case Credits" in chat_response.citations[0]["excerpt"]


def test_response_builder_filters_numeric_references_without_matching_values() -> None:
    """Numeric answers should not show unrelated references with different numbers."""
    retrieval_result = RetrievalResult(
        documents=[
            RetrievedDocument(
                id="relevant",
                title="CA-EN-Company-Policy.pdf",
                content=(
                    "An FBO reaches the level of Assistant Supervisor by generating a total of "
                    "2 Open Group Case Credits in any single Operating Company within any "
                    "2 consecutive Months."
                ),
                source="s3://kb/policy.pdf",
                excerpt="Assistant Supervisor requirement",
                page="6",
                score=0.72,
            ),
            RetrievedDocument(
                id="noise",
                title="CA-EN-Company-Policy.pdf",
                content="Chairman's Bonus Manager qualification requires 700 Open Group Case Credits.",
                source="s3://kb/policy.pdf",
                excerpt="Chairman's Bonus Manager qualification",
                page="26",
                score=0.93,
            ),
        ],
        citations=[],
        confidence=0.72,
    )
    model_response = ModelResponse(
        text="To become an Assistant Supervisor, you need 2 Open Group Case Credits within any 2 consecutive months.",
        citations=retrieval_result.sources,
        confidence=0.72,
        provider="claude",
        model_name="model",
    )

    chat_response = ResponseBuilder().build(
        model_response=model_response,
        retrieval_result=retrieval_result,
        correlation_id="cid",
    )

    assert [citation["page"] for citation in chat_response.citations] == ["6"]


def test_response_builder_does_not_attach_policy_sources_to_guardrail_copy() -> None:
    """Safety interventions must not make unrelated retrieval look like evidence."""
    document = RetrievedDocument(
        id="unrelated-policy",
        title="Policy - Sec 8.08: Sapphire Manager",
        content="Sapphire Manager qualification requirements.",
        source="s3://kb/policy.pdf",
        score=0.9,
    )
    response = ResponseBuilder().build(
        model_response=ModelResponse(
            text="I cannot provide medical advice.",
            citations=[document.to_source()],
            confidence=0.9,
            provider="claude",
            model_name="model",
            finish_reason="guardrail_intervened",
        ),
        retrieval_result=RetrievalResult(documents=[document], citations=[], confidence=0.9),
        correlation_id="cid",
    )

    assert response.citations == []
    assert response.metadata["failure_layer"] == "aws_guardrail"
    assert response.metadata["response_source"] == "guardrail"


def test_response_builder_does_not_attach_an_unrelated_source() -> None:
    """No reference is safer than displaying a policy section that does not support the reply."""
    document = RetrievedDocument(
        id="unrelated",
        title="Policy - Sec 8.08: Sapphire Manager",
        content="Sapphire Manager recognition requirements.",
        source="s3://kb/policy.pdf",
        score=0.9,
    )
    response = ResponseBuilder().build(
        model_response=ModelResponse(
            text="Please contact support for help with your account.",
            citations=[document.to_source()],
            confidence=0.9,
            provider="claude",
            model_name="model",
        ),
        retrieval_result=RetrievalResult(documents=[document], citations=[], confidence=0.9),
        correlation_id="cid",
    )

    assert response.citations == []


def test_verified_evidence_citation_survives_cross_language_answer() -> None:
    """Claim-verified evidence must not be dropped by language-sensitive token overlap."""
    document = RetrievedDocument(
        id="manager-requalification",
        title="Company Policy - Sec 4.02: Manager Requalification",
        content="A Manager may requalify under the conditions stated in this section.",
        source="s3://kb/policy.pdf",
        page="19",
        metadata={"section_id": "4.02", "section_title": "Manager Requalification"},
    )
    retrieval_result = RetrievalResult(
        documents=[document],
        citations=[document.to_source()],
        confidence=0.9,
        metadata={
            "evidence_contract": {
                "status": "accepted",
                "evidence_ids": ["manager-requalification"],
            }
        },
    )
    response = ResponseBuilder().build(
        model_response=ModelResponse(
            text="Een Manager kan zich opnieuw kwalificeren volgens de voorwaarden in dit onderdeel.",
            citations=[],
            confidence=0.9,
            provider="claude",
            model_name="model",
        ),
        retrieval_result=retrieval_result,
        correlation_id="cid",
    )
    assert len(response.citations) == 1
    assert response.citations[0]["section"] == "4.02"
    assert response.citations[0]["page"] == "19"
