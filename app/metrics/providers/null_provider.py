"""No-op metrics provider."""

from app.metrics.models import PipelineMetric, PipelineStageSnapshot, RequestMetric, RequestMetricSnapshot


class NullMetricsProvider:
    """Discard metrics without external side effects."""

    name = "null"

    def publish_request(self, metric: RequestMetric, snapshot: RequestMetricSnapshot) -> None:
        """Discard request metric."""
        return None

    def publish_pipeline(self, metric: PipelineMetric, snapshot: PipelineStageSnapshot) -> None:
        """Discard pipeline metric."""
        return None

    def flush(self) -> None:
        """Nothing to flush for the null provider."""
        return None
