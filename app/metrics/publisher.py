"""Structured metrics publisher."""

from config import settings

from .models import PipelineMetric, PipelineStageSnapshot, RequestMetric, RequestMetricSnapshot, SystemMetric
from .provider import MetricsProvider
from .registry import MetricsRegistry, metrics_registry
from utils.logging import get_logger

LOGGER = get_logger("app.metrics")


class MetricsPublisher:
    """Publish structured metrics to application logs."""

    def __init__(
        self,
        registry: MetricsRegistry | None = None,
        provider_name: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.registry = registry or metrics_registry
        self.provider_name = provider_name or settings.METRICS_PROVIDER
        self.enabled = settings.ENABLE_METRICS if enabled is None else enabled

    def publish_request(self, metric: RequestMetric, snapshot: RequestMetricSnapshot) -> None:
        """Publish one request metric sample with current aggregate counters."""
        if not self.enabled:
            return
        self.provider.publish_request(metric, snapshot)
        LOGGER.info(
            "request_metric_recorded",
            correlation_id=metric.correlation_id,
            method=metric.method,
            path=metric.path,
            status_code=metric.status_code,
            success=metric.success,
            duration_ms=metric.duration_ms,
            environment=metric.environment,
            version=metric.version,
            hostname=metric.hostname,
            request_count=snapshot.request_count,
            success_count=snapshot.success_count,
            failure_count=snapshot.failure_count,
            average_duration_ms=snapshot.average_duration_ms,
            dimensions=metric.dimensions,
        )

    def publish_pipeline(self, metric: PipelineMetric, snapshot: PipelineStageSnapshot) -> None:
        """Publish one pipeline stage timing metric."""
        if not self.enabled:
            return
        self.provider.publish_pipeline(metric, snapshot)
        LOGGER.info(
            "pipeline_metric_recorded",
            correlation_id=metric.correlation_id,
            stage=metric.stage,
            success=metric.success,
            duration_ms=metric.duration_ms,
            environment=metric.environment,
            version=metric.version,
            hostname=metric.hostname,
            stage_count=snapshot.count,
            average_duration_ms=snapshot.average_duration_ms,
            min_duration_ms=snapshot.min_duration_ms,
            max_duration_ms=snapshot.max_duration_ms,
            metadata=metric.metadata,
        )

    def publish_system(self, metric: SystemMetric) -> None:
        """Publish one system health metric."""
        if not self.enabled:
            return
        self.provider.publish_system(metric)
        LOGGER.info(
            "system_metric_recorded",
            name=metric.name,
            value=metric.value,
            unit=metric.unit,
            environment=metric.environment,
            version=metric.version,
            hostname=metric.hostname,
            metadata=metric.metadata,
        )

    def flush(self) -> None:
        """Flush the configured metrics provider."""
        if self.enabled:
            self.provider.flush()

    @property
    def provider(self) -> MetricsProvider:
        """Return the configured metrics provider."""
        return self.registry.get(self.provider_name)


metrics_publisher = MetricsPublisher()
