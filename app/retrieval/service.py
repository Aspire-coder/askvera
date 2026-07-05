"""Retrieval pipeline service."""

from .models import RetrievalResult
from .providers import BedrockRetrievalProvider, RetrievalProvider


class RetrievalService:
    """Coordinate retrieval pipeline stages."""

    def __init__(self, provider: RetrievalProvider | None = None) -> None:
        self.provider = provider or BedrockRetrievalProvider()

    def retrieve(self, message: str, country: str, language: str, role: str, correlation_id: str) -> RetrievalResult:
        """Return approved documents for a chat request."""
        return self.provider.retrieve(message, country, language, role, correlation_id)


retrieval_service = RetrievalService()
