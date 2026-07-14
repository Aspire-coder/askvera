"""Unit tests for Bedrock prompt rendering and response parsing."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models.bedrock_provider import BedrockClaudeProvider
from app.prompts import PromptBuilder
from app.retrieval import RetrievedDocument, RetrievalResult, confidence_from_sources
from utils.exceptions import LowConfidenceError


def test_build_prompt_replaces_all_variables() -> None:
    """The ASK Vera prompt contains concrete user context."""
    prompt = PromptBuilder().build(
        user_question="question",
        conversation="history",
        country="US",
        language="en",
        role="new_prospect",
        retrieved_documents="chunk",
    )
    assert "{{" not in prompt.system_prompt
    assert "US" in prompt.system_prompt
    assert "chunk" in prompt.system_prompt


def test_bedrock_provider_returns_sources() -> None:
    """Bedrock response is transformed into API data."""
    runtime = MagicMock()
    runtime.converse.return_value = {"output": {"message": {"content": [{"text": "Answer"}]}}}
    clients = SimpleNamespace(bedrock_runtime=runtime)
    retrieval_result = RetrievalResult(
        documents=[
            RetrievedDocument(
                id="doc",
                title="doc.pdf",
                content="excerpt",
                source="s3://kb/doc.pdf",
                excerpt="excerpt",
                page="4",
                document_version="v2",
                country="US",
                language="en",
                score=0.91,
            )
        ],
        citations=[],
        confidence=0.91,
    )
    with patch("app.models.bedrock_provider.get_aws_clients", return_value=clients):
        result = BedrockClaudeProvider().generate(
            build_prompt_package("q", "US", "en", "new_prospect", retrieval_result),
            retrieval_result,
            "cid",
        ).to_chat_result()
    assert result["response"] == "Answer"
    assert result["confidence"] >= 0.65
    assert result["sources"][0]["uri"] == "s3://kb/doc.pdf"
    assert result["sources"][0]["page"] == "4"
    assert result["sources"][0]["documentVersion"] == "v2"


def test_confidence_uses_scores_when_available() -> None:
    """Confidence uses retrieval scores rather than a binary source check."""
    confidence = confidence_from_sources([{"score": 0.7}, {"score": 0.9}])
    assert confidence == 0.87


def test_confidence_falls_back_to_citation_quality() -> None:
    """Confidence still works when Bedrock omits explicit scores."""
    confidence = confidence_from_sources(
        [
            {"uri": "s3://kb/one.pdf", "excerpt": "one"},
            {"uri": "s3://kb/two.pdf", "excerpt": "two"},
        ]
    )
    assert confidence > 0.65


def test_bedrock_provider_blocks_low_score_answer_with_sources() -> None:
    """Low retrieval scores should block before model generation, even with citations."""
    runtime = MagicMock()
    runtime.converse.return_value = {"output": {"message": {"content": [{"text": "Return policy answer"}]}}}
    clients = SimpleNamespace(bedrock_runtime=runtime)
    retrieval_result = RetrievalResult(
        documents=[
            RetrievedDocument(
                id="return-policy",
                title="return-policy.pdf",
                content="Return policy excerpt",
                source="s3://kb/return-policy.pdf",
                excerpt="Return policy excerpt",
                page="8",
                country="CA",
                language="en",
                score=0.39,
            )
        ],
        citations=[],
        confidence=0.39,
    )
    with patch("app.models.bedrock_provider.get_aws_clients", return_value=clients):
        with pytest.raises(LowConfidenceError):
            BedrockClaudeProvider().generate(
                build_prompt_package("return policy", "CA", "en", "new_prospect", retrieval_result),
                retrieval_result,
                "cid",
            )

    runtime.converse.assert_not_called()


def test_bedrock_provider_allows_borderline_confidence_with_enough_evidence() -> None:
    """Several plausible sources should be allowed through the model stage."""
    runtime = MagicMock()
    runtime.converse.return_value = {"output": {"message": {"content": [{"text": "Personal Retail Bonus answer"}]}}}
    clients = SimpleNamespace(bedrock_runtime=runtime)
    scores = [0.45370057, 0.40369812, 0.40310252, 0.43882382, 0.45370057]
    retrieval_result = RetrievalResult(
        documents=[
            RetrievedDocument(
                id=f"policy-{index}",
                title="CA-EN-Company-Policy.pdf",
                content="Personal Retail Bonus policy excerpt",
                source="s3://kb/CA-EN-Company-Policy.pdf",
                excerpt="Personal Retail Bonus policy excerpt",
                page=str(index),
                country="CA",
                language="en",
                score=score,
            )
            for index, score in enumerate(scores, start=1)
        ],
        citations=[],
        confidence=0.447,
    )

    with patch("app.models.bedrock_provider.get_aws_clients", return_value=clients):
        result = BedrockClaudeProvider().generate(
            build_prompt_package(
                "What is the Personal Retail Bonus %?",
                "CA",
                "en",
                "new_prospect",
                retrieval_result,
            ),
            retrieval_result,
            "cid",
        ).to_chat_result()

    assert result["response"] == "Personal Retail Bonus answer"
    runtime.converse.assert_called_once()


def test_bedrock_provider_raises_when_no_sources_are_available() -> None:
    """No citations and no retrieve fallback sources should still produce the fallback."""
    retrieval_result = RetrievalResult(documents=[], citations=[], confidence=0.0)

    with pytest.raises(LowConfidenceError):
        BedrockClaudeProvider().generate(
            build_prompt_package("unrelated", "CA", "en", "new_prospect", retrieval_result),
            retrieval_result,
            "cid",
        )


def build_prompt_package(message: str, country: str, language: str, role: str, retrieval_result: RetrievalResult):
    from app.prompts import PromptBuilder

    return PromptBuilder().build(
        user_question=message,
        conversation="",
        country=country,
        language=language,
        role=role,
        retrieval_result=retrieval_result,
    )
