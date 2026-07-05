"""Pipeline timing helpers."""

from .collector import MetricsCollector, metrics_collector
from .models import PipelineMetric
from .publisher import MetricsPublisher, metrics_publisher


def record_pipeline_metric(
    *,
    stage: str,
    duration_ms: float,
    success: bool,
    correlation_id: str,
    metadata: dict | None = None,
    collector: MetricsCollector | None = None,
    publisher: MetricsPublisher | None = None,
) -> None:
    """Record and publish one pipeline stage timing metric."""
    metric = PipelineMetric(
        stage=stage,
        duration_ms=duration_ms,
        success=success,
        correlation_id=correlation_id,
        metadata=metadata or {},
    )
    selected_collector = collector or metrics_collector
    selected_publisher = publisher or metrics_publisher
    snapshot = selected_collector.record_pipeline(metric)
    selected_publisher.publish_pipeline(metric, snapshot)
