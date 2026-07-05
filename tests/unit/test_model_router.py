"""Unit tests for model routing."""

from app.models import ModelRegistry, ModelResponse, ModelRouter
from app.prompts import PromptPackage
from app.retrieval import RetrievalResult


class FakeProvider:
    name = "fake"

    def generate(self, prompt: PromptPackage, retrieval_result: RetrievalResult, correlation_id: str) -> ModelResponse:
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
