"""Metrics provider registry."""

from .provider import MetricsProvider
from .providers import CloudWatchMetricsProvider, NullMetricsProvider


class MetricsRegistry:
    """Keep metrics providers addressable by stable names."""

    def __init__(self) -> None:
        self._providers: dict[str, MetricsProvider] = {}

    def register(self, provider: MetricsProvider) -> None:
        """Register one metrics provider."""
        self._providers[provider.name] = provider

    def get(self, name: str) -> MetricsProvider:
        """Return a registered metrics provider by name."""
        try:
            return self._providers[name]
        except KeyError as exc:
            available = ", ".join(sorted(self._providers)) or "none"
            raise ValueError(f"Unknown metrics provider '{name}'. Available providers: {available}") from exc


metrics_registry = MetricsRegistry()
metrics_registry.register(NullMetricsProvider())
metrics_registry.register(CloudWatchMetricsProvider())
