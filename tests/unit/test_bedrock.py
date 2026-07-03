"""Unit tests for Bedrock prompt rendering and response parsing."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from services.bedrock import _confidence_from_sources, build_prompt, retrieve_and_generate
from utils.exceptions import LowConfidenceError


def test_build_prompt_replaces_all_variables() -> None:
    """The ASK Vera prompt contains concrete user context."""
    prompt = build_prompt("en", "US", "new_prospect", "chunk", "history")
    assert "{{" not in prompt
    assert "US" in prompt
    assert "chunk" in prompt


def test_retrieve_and_generate_returns_sources() -> None:
    """Bedrock response is transformed into API data."""
    runtime = MagicMock()
    runtime.retrieve_and_generate.return_value = {
        "output": {"text": "Answer"},
        "citations": [
            {
                "retrievedReferences": [
                    {
                        "location": {"s3Location": {"uri": "s3://kb/doc.pdf"}},
                        "content": {"text": "excerpt"},
                        "metadata": {"score": 0.91, "page": 4, "document_version": "v2", "country_code": "US", "language": "en"},
                    }
                ]
            }
        ],
    }
    clients = SimpleNamespace(bedrock_agent_runtime=runtime)
    with patch("services.bedrock.get_aws_clients", return_value=clients):
        result = retrieve_and_generate("q", "US", "en", "new_prospect", "", "cid")
    assert result["response"] == "Answer"
    assert result["confidence"] >= 0.65
    assert result["sources"][0]["uri"] == "s3://kb/doc.pdf"
    assert result["sources"][0]["page"] == "4"
    assert result["sources"][0]["documentVersion"] == "v2"


def test_confidence_uses_scores_when_available() -> None:
    """Confidence uses retrieval scores rather than a binary source check."""
    confidence = _confidence_from_sources([{"score": 0.7}, {"score": 0.9}])
    assert confidence == 0.87


def test_confidence_falls_back_to_citation_quality() -> None:
    """Confidence still works when Bedrock omits explicit scores."""
    confidence = _confidence_from_sources(
        [
            {"uri": "s3://kb/one.pdf", "excerpt": "one"},
            {"uri": "s3://kb/two.pdf", "excerpt": "two"},
        ]
    )
    assert confidence > 0.65


def test_retrieve_and_generate_returns_low_score_answer_with_sources() -> None:
    """Low retrieval scores should be logged, not rejected, when citations exist."""
    runtime = MagicMock()
    runtime.retrieve_and_generate.return_value = {
        "output": {"text": "Return policy answer"},
        "citations": [
            {
                "retrievedReferences": [
                    {
                        "location": {"s3Location": {"uri": "s3://kb/return-policy.pdf"}},
                        "content": {"text": "Return policy excerpt"},
                        "metadata": {"score": 0.39, "page": 8, "country_code": "CA", "language": "en"},
                    }
                ]
            }
        ],
    }
    clients = SimpleNamespace(bedrock_agent_runtime=runtime)
    with patch("services.bedrock.get_aws_clients", return_value=clients):
        result = retrieve_and_generate("return policy", "CA", "en", "new_prospect", "", "cid")

    assert result["response"] == "Return policy answer"
    assert result["confidence"] < 0.5
    assert result["sources"][0]["uri"] == "s3://kb/return-policy.pdf"


def test_retrieve_and_generate_raises_when_no_sources_after_fallback() -> None:
    """No citations and no retrieve fallback sources should still produce the fallback."""
    runtime = MagicMock()
    runtime.retrieve_and_generate.return_value = {"output": {"text": "Ungrounded answer"}, "citations": []}
    runtime.retrieve.return_value = {"retrievalResults": []}
    clients = SimpleNamespace(bedrock_agent_runtime=runtime)

    with patch("services.bedrock.get_aws_clients", return_value=clients), pytest.raises(LowConfidenceError):
        retrieve_and_generate("unrelated", "CA", "en", "new_prospect", "", "cid")
