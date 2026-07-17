"""Model routing layer."""

from time import perf_counter

from app.metrics import STAGE_MODEL_GENERATE
from app.metrics.pipeline import record_pipeline_metric
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
        started = perf_counter()
        success = False
        provider_name = self.default_provider
        response: ModelResponse | None = None
        try:
            provider = self.registry.get(self.default_provider)
            provider_name = provider.name
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
            response = provider.generate(prompt, retrieval_result, correlation_id)
            success = True
            return response
        finally:
            usage = response.token_usage if response and isinstance(response.token_usage, dict) else {}
            record_pipeline_metric(
                stage=STAGE_MODEL_GENERATE,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                success=success,
                correlation_id=correlation_id,
                metadata={
                    "provider": response.provider if response else provider_name,
                    "model": response.model_name if response else "",
                    "sourceCount": len(retrieval_result.documents),
                    "inputTokens": int(usage.get("inputTokens", usage.get("input_tokens", 0)) or 0),
                    "outputTokens": int(usage.get("outputTokens", usage.get("output_tokens", 0)) or 0),
                    "finishReason": response.finish_reason if response else "",
                },
            )


model_router = ModelRouter()
