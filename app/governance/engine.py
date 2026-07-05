"""Governance engine entry point."""

from utils.logging import get_logger

from .models import GovernanceDecision
from .registry import GovernanceRegistry, governance_registry

LOGGER = get_logger("app.governance")


class GovernanceEngine:
    """Delegate governance evaluation to the configured provider."""

    def __init__(self, registry: GovernanceRegistry | None = None, default_provider: str = "bedrock_guardrails") -> None:
        self.registry = registry or governance_registry
        self.default_provider = default_provider

    def evaluate(self, *, text: str, country: str, language: str, correlation_id: str) -> GovernanceDecision:
        """Evaluate text through the configured governance provider."""
        provider = self.registry.get(self.default_provider)
        LOGGER.info(
            "governance_provider_selected",
            correlation_id=correlation_id,
            provider=provider.name,
            configured_provider=self.default_provider,
            country=country,
            language=language,
        )
        return provider.evaluate(text=text, country=country, language=language, correlation_id=correlation_id)


governance_engine = GovernanceEngine()
