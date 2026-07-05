"""Metrics provider interface."""

from typing import Protocol

from .models import PipelineMetric, PipelineStageSnapshot, RequestMetric, RequestMetricSnapshot


class MetricsProvider(Protocol):
    """Interface implemented by metrics backends."""

    name: str

    def publish_request(self, metric: RequestMetric, snapshot: RequestMetricSnapshot) -> None:
        """Publish one request metric sample."""
        ...

    def publish_pipeline(self, metric: PipelineMetric, snapshot: PipelineStageSnapshot) -> None:
        """Publish one pipeline stage metric sample."""
        ...

    def flush(self) -> None:
        """Flush any buffered metrics."""
        ...
