"""Retrieval pipeline service."""

from time import perf_counter

from app.metrics import STAGE_RETRIEVAL
from app.metrics.pipeline import record_pipeline_metric
from config import settings

from .models import RetrievalResult
from .providers import BedrockRetrievalProvider, RetrievalProvider


class RetrievalService:
    """Coordinate retrieval pipeline stages."""

    def __init__(self, provider: RetrievalProvider | None = None) -> None:
        self._fixed_provider = provider is not None
        self._provider_name = settings.RETRIEVAL_PROVIDER
        self.provider = provider or self._default_provider()

    def _default_provider(self) -> RetrievalProvider:
        """Select the configured retrieval backend."""
        return self._provider_for_name(
            settings.RETRIEVAL_PROVIDER,
            enable_bedrock_rerank=settings.OPENSEARCH_LIVE_RERANK_ENABLED,
        )

    @staticmethod
    def _provider_for_name(
        provider_name: str,
        *,
        index_name: str | None = None,
        enable_bedrock_rerank: bool = False,
    ) -> RetrievalProvider:
        """Build a provider without changing the established live selection."""
        if provider_name == "opensearch_section":
            from .opensearch_sections import OpenSearchSectionProvider

            return OpenSearchSectionProvider(
                index_name=index_name,
                enable_bedrock_rerank=enable_bedrock_rerank,
            )
        return BedrockRetrievalProvider()

    def _current_provider(self) -> RetrievalProvider:
        """Return a provider that matches the latest loaded configuration."""
        if not self._fixed_provider and self._provider_name != settings.RETRIEVAL_PROVIDER:
            self.provider = self._default_provider()
            self._provider_name = settings.RETRIEVAL_PROVIDER
        return self.provider

    def retrieve(self, message: str, country: str, language: str, role: str, correlation_id: str) -> RetrievalResult:
        """Return approved documents for a chat request."""
        started = perf_counter()
        success = False
        result: RetrievalResult | None = None
        provider = self._current_provider()
        try:
            result = provider.retrieve(message, country, language, role, correlation_id)
            success = True
            return result
        finally:
            record_pipeline_metric(
                stage=STAGE_RETRIEVAL,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                success=success,
                correlation_id=correlation_id,
                metadata={
                    "country": country,
                    "language": language,
                    "role": role,
                    "provider": type(provider).__name__,
                    "sourceCount": len(result.documents) if result else 0,
                    "confidence": round(float(result.confidence), 3) if result else 0.0,
                },
            )


retrieval_service = RetrievalService()
