"""Model routing layer."""

from app.prompts import PromptPackage
from app.retrieval import RetrievalResult
from config import settings
from utils.logging import get_logger

from .registry import ModelRegistry, model_registry
from .responses import ModelResponse

LOGGER = get_logger("app.models.router")


class ModelRouter:
    """Route prompt packages to the configured model provider."""

    def __init__(self, registry: ModelRegistry | None = None, default_provider: str | None = None) -> None:
        self.registry = registry or model_registry
        self.default_provider = default_provider or settings.DEFAULT_MODEL_PROVIDER

    def generate(self, prompt: PromptPackage, retrieval_result: RetrievalResult, correlation_id: str) -> ModelResponse:
        """Generate through the configured provider."""
        provider = self.registry.get(self.default_provider)
        LOGGER.info(
            "model_router_provider_selected",
            correlation_id=correlation_id,
            provider=provider.name,
            configured_provider=self.default_provider,
            country=prompt.country,
            language=prompt.language,
            role=prompt.role,
            source_count=len(retrieval_result.documents),
            confidence=retrieval_result.confidence,
        )
        return provider.generate(prompt, retrieval_result, correlation_id)


model_router = ModelRouter()
