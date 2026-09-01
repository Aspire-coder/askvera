"""Unit tests for model routing."""

import pytest

from app.models.registry import ModelRegistry
from app.models.responses import ModelResponse
from app.models.router import ModelRouter
from app.prompts import PromptPackage
from app.retrieval import RetrievedDocument, RetrievalResult


class FakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self.last_prompt: PromptPackage | None = None

    def generate(self, prompt: PromptPackage, retrieval_result: RetrievalResult, correlation_id: str) -> ModelResponse:
        self.last_prompt = prompt
        return ModelResponse(
            text=f"handled:{prompt.user_prompt}",
            citations=retrieval_result.sources,
            confidence=retrieval_result.confidence,
            provider=self.name,
            model_name="fake-model",
            metadata={"correlation_id": correlation_id},
        )


def test_model_router_uses_configured_provider() -> None:
    """Router delegates generation to the selected provider."""
    registry = ModelRegistry()
    registry.register(FakeProvider())
    router = ModelRouter(registry=registry, default_provider="fake")
    response = router.generate(
        PromptPackage(
            system_prompt="system",
            user_prompt="question",
            retrieved_context="context",
            country="US",
            language="en",
            role="new_prospect",
        ),
        RetrievalResult(documents=[], citations=[], confidence=0.7),
        "cid",
    )

    assert response.text == "handled:question"
    assert response.provider == "fake"
    assert response.metadata["correlation_id"] == "cid"


def _retrieval_result(*, confidence: float = 0.9, source: str = "s3://kb/policy.pdf") -> RetrievalResult:
    return RetrievalResult(
        documents=[
            RetrievedDocument(
                id="policy-section",
                title="Policy",
                content="Approved evidence",
                source=source,
                country="US",
                language="en",
                score=confidence,
            )
        ],
        citations=[],
        confidence=confidence,
    )


def _prompt(question: str, *, has_conversation: bool = False) -> PromptPackage:
    return PromptPackage(
        system_prompt="system",
        user_prompt=question,
        retrieved_context="context",
        country="US",
        language="en",
        role="new_prospect",
        metadata={"user_question": question, "has_conversation": has_conversation},
    )


def _routing_settings(monkeypatch, mode: str) -> None:
    monkeypatch.setattr("app.models.model_routing.settings.MODEL_ROUTING_MODE", mode)
    monkeypatch.setattr("app.models.model_routing.settings.BEDROCK_MODEL_ARN", "production-model")
    monkeypatch.setattr("app.models.model_routing.settings.BEDROCK_FAST_MODEL_ID", "fast-model")
    monkeypatch.setattr("app.models.model_routing.settings.BEDROCK_COMPLEX_MODEL_ID", "complex-model")
    monkeypatch.setattr("app.models.model_routing.settings.MODEL_ROUTING_FAST_MIN_CONFIDENCE", 0.75)
    monkeypatch.setattr("app.models.model_routing.settings.MODEL_ROUTING_FAST_MAX_DISTINCT_SOURCES", 1)
    monkeypatch.setattr("app.models.model_routing.settings.MODEL_ROUTING_FAST_MAX_QUESTION_CHARS", 220)


def test_shadow_mode_records_fast_route_without_changing_generation_model(monkeypatch) -> None:
    """Shadow evaluation must never alter the model used for production answers."""
    _routing_settings(monkeypatch, "shadow")
    provider = FakeProvider()
    registry = ModelRegistry()
    registry.register(provider)

    response = ModelRouter(registry=registry, default_provider="fake").generate(
        _prompt("How do I sign up?"),
        _retrieval_result(),
        "cid",
    )

    assert provider.last_prompt is not None
    assert "generation_model_id" not in provider.last_prompt.metadata
    assert response.metadata["model_route_target"] == "fast"
    assert response.metadata["model_route_would_use_fast"] is True
    assert response.metadata["model_route_live"] is False


def test_live_mode_routes_low_risk_question_to_fast_model(monkeypatch) -> None:
    """A simple, well-supported question may use the configured fast model."""
    _routing_settings(monkeypatch, "live")
    provider = FakeProvider()
    registry = ModelRegistry()
    registry.register(provider)

    ModelRouter(registry=registry, default_provider="fake").generate(
        _prompt("Comment puis-je m'inscrire ?"),
        _retrieval_result(),
        "cid",
    )

    assert provider.last_prompt is not None
    assert provider.last_prompt.metadata["generation_model_id"] == "fast-model"
    assert provider.last_prompt.metadata["model_route_reasons"] == ["low_risk_evidence"]


def test_follow_up_question_routes_to_complex_model(monkeypatch) -> None:
    """Conversation-dependent follow-ups remain on the stronger model."""
    _routing_settings(monkeypatch, "live")
    provider = FakeProvider()
    registry = ModelRegistry()
    registry.register(provider)

    ModelRouter(registry=registry, default_provider="fake").generate(
        _prompt("I need more details", has_conversation=True),
        _retrieval_result(),
        "cid",
    )

    assert provider.last_prompt is not None
    assert provider.last_prompt.metadata["generation_model_id"] == "complex-model"
    assert "conversation_context" in provider.last_prompt.metadata["model_route_reasons"]


@pytest.mark.parametrize(
    ("question", "confidence", "reason"),
    [
        ("What is the minimum order of EUR 50?", 0.9, "explicit_numeric_claim"),
        ("What is required? What is excluded?", 0.9, "multi_part_question"),
        ("ما المتطلبات؟ وما الاستثناءات؟", 0.9, "multi_part_question"),
        ("Explain the policy", 0.6, "lower_confidence"),
    ],
)
def test_risk_signals_route_to_complex_model(monkeypatch, question, confidence, reason) -> None:
    """Language-neutral structural risk signals choose the stronger model."""
    _routing_settings(monkeypatch, "live")
    provider = FakeProvider()
    registry = ModelRegistry()
    registry.register(provider)

    ModelRouter(registry=registry, default_provider="fake").generate(
        _prompt(question),
        _retrieval_result(confidence=confidence),
        "cid",
    )

    assert provider.last_prompt is not None
    assert provider.last_prompt.metadata["generation_model_id"] == "complex-model"
    assert reason in provider.last_prompt.metadata["model_route_reasons"]


def test_multiple_source_documents_route_to_complex_model(monkeypatch) -> None:
    """Synthesis across documents uses the stronger model."""
    _routing_settings(monkeypatch, "live")
    provider = FakeProvider()
    registry = ModelRegistry()
    registry.register(provider)
    retrieval_result = _retrieval_result()
    retrieval_result = RetrievalResult(
        documents=[
            *retrieval_result.documents,
            RetrievedDocument(
                id="directory-section",
                title="Directory",
                content="Approved directory evidence",
                source="s3://kb/directory.pdf",
                country="GLOBAL",
                language="en",
                score=0.9,
            ),
        ],
        citations=[],
        confidence=0.9,
    )

    ModelRouter(registry=registry, default_provider="fake").generate(
        _prompt("Explain the requirements"),
        retrieval_result,
        "cid",
    )

    assert provider.last_prompt is not None
    reasons = provider.last_prompt.metadata["model_route_reasons"]
    assert "multiple_documents" in reasons
    assert "cross_market_evidence" in reasons


def test_structured_table_evidence_routes_to_complex_model(monkeypatch) -> None:
    """Table interpretation remains on the stronger model."""
    _routing_settings(monkeypatch, "live")
    provider = FakeProvider()
    registry = ModelRegistry()
    registry.register(provider)
    retrieval_result = RetrievalResult(
        documents=[
            RetrievedDocument(
                id="table-row",
                title="Policy table",
                content="Approved table row",
                source="s3://kb/policy.pdf",
                country="US",
                language="en",
                score=0.9,
                metadata={"is_table": True},
            )
        ],
        citations=[],
        confidence=0.9,
    )

    ModelRouter(registry=registry, default_provider="fake").generate(
        _prompt("Explain this requirement"),
        retrieval_result,
        "cid",
    )

    assert provider.last_prompt is not None
    assert "structured_evidence" in provider.last_prompt.metadata["model_route_reasons"]
