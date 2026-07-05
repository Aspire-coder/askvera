"""Unit tests for metrics provider registry."""

from app.metrics.providers import NullMetricsProvider
from app.metrics.registry import MetricsRegistry


def test_metrics_registry_returns_registered_provider() -> None:
    registry = MetricsRegistry()
    provider = NullMetricsProvider()

    registry.register(provider)

    assert registry.get("null") is provider


def test_metrics_registry_rejects_unknown_provider() -> None:
    registry = MetricsRegistry()

    try:
        registry.get("missing")
    except ValueError as exc:
        assert "Unknown metrics provider" in str(exc)
    else:
        raise AssertionError("Expected unknown provider lookup to fail.")
