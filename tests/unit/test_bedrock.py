"""Unit tests for Bedrock prompt rendering and response parsing."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.models.bedrock_provider import BedrockClaudeProvider, _reset_circuit_breaker
from app.prompts import PromptBuilder
from app.retrieval import RetrievedDocument, RetrievalResult, confidence_from_sources
from utils.exceptions import BedrockServiceError, LowConfidenceError


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
    assert prompt.prompt_version == "2026-07-17.1"


def test_fixed_prompt_is_compact_without_losing_grounding_rules() -> None:
    """Static instructions stay compact while preserving answer safeguards."""
    prompt = PromptBuilder().build(
        user_question="question",
        conversation="",
        country="CA",
        language="fr",
        role="new_prospect",
        retrieved_documents="",
    )

    normalized_prompt = " ".join(prompt.system_prompt.split())
    assert len(prompt.system_prompt) < 4000
    assert "complete response in that language" in normalized_prompt
    assert "Use only the retrieved authorised chunks" in normalized_prompt
    assert "Numbers, percentages, dates, timeframes" in normalized_prompt
    assert "Never combine countries" in normalized_prompt
    assert "do not suggest replacement testimonials" in normalized_prompt
    assert "history only for conversational continuity" in normalized_prompt


def test_prompt_context_exposes_exact_evidence_identity_and_location() -> None:
    """The evidence contract receives stable IDs and user-facing citation metadata."""
    document = RetrievedDocument(
        id="policy-4-01-e",
        title="Benelux Policy",
        content="Approved policy content.",
        source="s3://kb/benelux-policy.pdf",
        page="18",
        metadata={"section_id": "4.01e", "section_title": "Case Credits"},
    )
    prompt = PromptBuilder().build(
        user_question="question",
        conversation="",
        country="NL",
        language="nl",
        role="new_prospect",
        retrieval_result=RetrievalResult(documents=[document], citations=[], confidence=0.9),
    )
    assert "Source ID: policy-4-01-e" in prompt.retrieved_context
    assert "Policy section: 4.01e" in prompt.retrieved_context
    assert "Page: 18" in prompt.retrieved_context
    assert document.to_source()["section"] == "4.01e"
    assert document.to_source()["sectionTitle"] == "Case Credits"


def test_prompt_context_exposes_structured_directory_fields() -> None:
    document = RetrievedDocument(
        id="directory-mexico",
        title="Global directory - Mexico",
        content="Mexico office raw content",
        source="s3://kb/global-directory.pdf",
        metadata={
            "directory_fields": {
                "Physical Address": "Londres No. 61, Torre A",
                "Office Phone 1": "52 55 3300 9400",
            }
        },
    )

    prompt = PromptBuilder().build(
        user_question="Mexico office details",
        conversation="",
        country="CA",
        language="en",
        role="new_prospect",
        retrieval_result=RetrievalResult(documents=[document], citations=[], confidence=0.9),
    )

    assert "Approved directory fields:" in prompt.retrieved_context
    assert "Physical Address: Londres No. 61, Torre A" in prompt.retrieved_context
    assert "Office Phone 1: 52 55 3300 9400" in prompt.retrieved_context


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
    converse_params = runtime.converse.call_args.kwargs
    assert converse_params["inferenceConfig"] == {"maxTokens": 1024}


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


def test_bedrock_provider_uses_configured_fallback_for_transient_failure(monkeypatch) -> None:
    """A throttled primary model can fail over without bypassing the normal prompt."""
    _reset_circuit_breaker()
    runtime = MagicMock()
    runtime.converse.side_effect = [
        ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "slow down"}, "ResponseMetadata": {"HTTPStatusCode": 429}},
            "Converse",
        ),
        {"output": {"message": {"content": [{"text": "Fallback answer"}]}}},
    ]
    monkeypatch.setattr("app.models.bedrock_provider.get_aws_clients", lambda: SimpleNamespace(bedrock_runtime=runtime))
    monkeypatch.setattr("app.models.bedrock_provider.settings.BEDROCK_FALLBACK_MODEL_ARN", "fallback-model")
    retrieval_result = RetrievalResult(
        documents=[RetrievedDocument(id="doc", title="doc", content="evidence", source="s3://kb/doc", score=0.9)],
        citations=[],
        confidence=0.9,
    )

    result = BedrockClaudeProvider().generate(
        build_prompt_package("question", "US", "en", "new_prospect", retrieval_result),
        retrieval_result,
        "cid",
    )

    assert result.text == "Fallback answer"
    assert result.model_name == "fallback-model"
    assert result.metadata["model_fallback_used"] is True
    assert [call.kwargs["modelId"] for call in runtime.converse.call_args_list] == [
        "arn:aws:bedrock:us-east-1:615592621509:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0",
        "fallback-model",
    ]


def test_bedrock_provider_does_not_fallback_for_non_transient_error(monkeypatch) -> None:
    """Permission errors should surface instead of being hidden by another model."""
    _reset_circuit_breaker()
    runtime = MagicMock()
    runtime.converse.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}, "ResponseMetadata": {"HTTPStatusCode": 403}},
        "Converse",
    )
    monkeypatch.setattr("app.models.bedrock_provider.get_aws_clients", lambda: SimpleNamespace(bedrock_runtime=runtime))
    monkeypatch.setattr("app.models.bedrock_provider.settings.BEDROCK_FALLBACK_MODEL_ARN", "fallback-model")
    retrieval_result = RetrievalResult(
        documents=[RetrievedDocument(id="doc", title="doc", content="evidence", source="s3://kb/doc", score=0.9)],
        citations=[],
        confidence=0.9,
    )

    with pytest.raises(BedrockServiceError):
        BedrockClaudeProvider().generate(
            build_prompt_package("question", "US", "en", "new_prospect", retrieval_result),
            retrieval_result,
            "cid",
        )

    assert runtime.converse.call_count == 1


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
