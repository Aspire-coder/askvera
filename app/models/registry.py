"""Model provider registry."""

from .bedrock_provider import BedrockClaudeProvider
from .provider import ModelProvider


class ModelRegistry:
    """Keep model providers addressable by stable names."""

    def __init__(self) -> None:
        self._providers: dict[str, ModelProvider] = {}

    def register(self, provider: ModelProvider) -> None:
        """Register one model provider."""
        self._providers[provider.name] = provider

    def get(self, name: str) -> ModelProvider:
        """Return a registered provider by name."""
        try:
            return self._providers[name]
        except KeyError as exc:
            available = ", ".join(sorted(self._providers)) or "none"
            raise ValueError(f"Unknown model provider '{name}'. Available providers: {available}") from exc


model_registry = ModelRegistry()
model_registry.register(BedrockClaudeProvider())
