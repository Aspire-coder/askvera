"""Governance provider registry."""

from .provider import GovernanceProvider
from .providers import BedrockGuardrailsProvider


class GovernanceRegistry:
    """Keep governance providers addressable by stable names."""

    def __init__(self) -> None:
        self._providers: dict[str, GovernanceProvider] = {}

    def register(self, provider: GovernanceProvider) -> None:
        """Register one governance provider."""
        self._providers[provider.name] = provider

    def get(self, name: str) -> GovernanceProvider:
        """Return a registered governance provider by name."""
        try:
            return self._providers[name]
        except KeyError as exc:
            available = ", ".join(sorted(self._providers)) or "none"
            raise ValueError(f"Unknown governance provider '{name}'. Available providers: {available}") from exc


governance_registry = GovernanceRegistry()
governance_registry.register(BedrockGuardrailsProvider())
