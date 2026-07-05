"""Structured metrics publisher."""

from .models import PipelineMetric, PipelineStageSnapshot, RequestMetric, RequestMetricSnapshot
from utils.logging import get_logger

LOGGER = get_logger("app.metrics")


class MetricsPublisher:
    """Publish structured metrics to application logs."""

    def publish_request(self, metric: RequestMetric, snapshot: RequestMetricSnapshot) -> None:
        """Publish one request metric sample with current aggregate counters."""
        LOGGER.info(
            "request_metric_recorded",
            correlation_id=metric.correlation_id,
            method=metric.method,
            path=metric.path,
            status_code=metric.status_code,
            success=metric.success,
            duration_ms=metric.duration_ms,
            request_count=snapshot.request_count,
            success_count=snapshot.success_count,
            failure_count=snapshot.failure_count,
            average_duration_ms=snapshot.average_duration_ms,
            dimensions=metric.dimensions,
        )

    def publish_pipeline(self, metric: PipelineMetric, snapshot: PipelineStageSnapshot) -> None:
        """Publish one pipeline stage timing metric."""
        LOGGER.info(
            "pipeline_metric_recorded",
            correlation_id=metric.correlation_id,
            stage=metric.stage,
            success=metric.success,
            duration_ms=metric.duration_ms,
            stage_count=snapshot.count,
            average_duration_ms=snapshot.average_duration_ms,
            min_duration_ms=snapshot.min_duration_ms,
            max_duration_ms=snapshot.max_duration_ms,
            metadata=metric.metadata,
        )


metrics_publisher = MetricsPublisher()
