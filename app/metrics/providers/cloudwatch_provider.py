"""CloudWatch metrics provider."""

from __future__ import annotations

from datetime import datetime
from threading import RLock
from typing import Any

from config import settings
from utils.logging import get_logger

from app.metrics.models import PipelineMetric, PipelineStageSnapshot, RequestMetric, RequestMetricSnapshot, SystemMetric

LOGGER = get_logger("app.metrics.cloudwatch")

CLOUDWATCH_METRIC_NAMES = {
    "request_count": "RequestCount",
    "request_duration": "RequestDuration",
    "governance": "GovernanceLatency",
    "retrieval": "RetrievalLatency",
    "prompt_build": "PromptBuildLatency",
    "model_generate": "ModelLatency",
    "validation": "ValidationLatency",
    "response_build": "ResponseBuildLatency",
    "cache_hit_ratio": "CacheHitRatio",
    "audit_queue_depth": "AuditQueueDepth",
}


class CloudWatchMetricsProvider:
    """Publish request, pipeline, and system metrics to CloudWatch."""

    name = "cloudwatch"

    def __init__(
        self,
        client: Any | None = None,
        enabled: bool | None = None,
        namespace: str | None = None,
        batch_size: int | None = None,
    ) -> None:
        self.enabled = settings.ENABLE_CLOUDWATCH_METRICS if enabled is None else enabled
        self.namespace = namespace or settings.CLOUDWATCH_NAMESPACE
        self.batch_size = batch_size or settings.CLOUDWATCH_BATCH_SIZE
        self.flush_interval = settings.CLOUDWATCH_FLUSH_INTERVAL
        self._lock = RLock()
        self._pending: list[dict[str, Any]] = []
        self.client = client
        if self.enabled and self.client is None:
            self.client = self._build_client()

    def publish_request(self, metric: RequestMetric, snapshot: RequestMetricSnapshot) -> None:
        """Publish one request metric sample."""
        if not self.enabled:
            return
        self._queue_metric(
            {
                "MetricName": CLOUDWATCH_METRIC_NAMES["request_count"],
                "Dimensions": self._base_dimensions(metric.environment, metric.version, metric.hostname)
                + [
                    {"Name": "Method", "Value": metric.method},
                    {"Name": "Path", "Value": metric.path},
                    {"Name": "StatusCode", "Value": str(metric.status_code)},
                ],
                "Timestamp": self._timestamp(metric.timestamp),
                "Value": 1.0,
                "Unit": "Count",
            }
        )
        self._queue_metric(
            {
                "MetricName": CLOUDWATCH_METRIC_NAMES["request_duration"],
                "Dimensions": self._base_dimensions(metric.environment, metric.version, metric.hostname)
                + [
                    {"Name": "Method", "Value": metric.method},
                    {"Name": "Path", "Value": metric.path},
                ],
                "Timestamp": self._timestamp(metric.timestamp),
                "Value": metric.duration_ms,
                "Unit": "Milliseconds",
            }
        )

    def publish_pipeline(self, metric: PipelineMetric, snapshot: PipelineStageSnapshot) -> None:
        """Publish one pipeline stage timing metric."""
        if not self.enabled:
            return
        self._queue_metric(
            {
                "MetricName": CLOUDWATCH_METRIC_NAMES.get(metric.stage, self._metric_name(metric.stage)),
                "Dimensions": self._base_dimensions(metric.environment, metric.version, metric.hostname)
                + [{"Name": "Stage", "Value": metric.stage}],
                "Timestamp": self._timestamp(metric.timestamp),
                "Value": metric.duration_ms,
                "Unit": "Milliseconds",
            }
        )

    def publish_system(self, metric: SystemMetric) -> None:
        """Publish one system metric sample."""
        if not self.enabled:
            return
        self._queue_metric(
            {
                "MetricName": CLOUDWATCH_METRIC_NAMES.get(metric.name, self._metric_name(metric.name)),
                "Dimensions": self._base_dimensions(metric.environment, metric.version, metric.hostname),
                "Timestamp": metric.timestamp,
                "Value": metric.value,
                "Unit": self._cloudwatch_unit(metric.unit),
            }
        )

    def flush(self) -> None:
        """Flush pending metric data to CloudWatch."""
        if not self.enabled or not self.client:
            return
        with self._lock:
            if not self._pending:
                return
            batches = [
                self._pending[index : index + self.batch_size]
                for index in range(0, len(self._pending), self.batch_size)
            ]
            self._pending = []

        for batch in batches:
            try:
                self.client.put_metric_data(Namespace=self.namespace, MetricData=batch)
            except Exception as exc:  # noqa: BLE001 - metrics must never break app requests.
                LOGGER.warning(
                    "cloudwatch_metric_publish_failed",
                    namespace=self.namespace,
                    batch_size=len(batch),
                    error=str(exc),
                )

    def _queue_metric(self, metric_data: dict[str, Any]) -> None:
        with self._lock:
            self._pending.append(metric_data)
            should_flush = len(self._pending) >= self.batch_size
        if should_flush:
            self.flush()

    def _build_client(self) -> Any | None:
        try:
            import boto3

            return boto3.client("cloudwatch", region_name=settings.AWS_REGION)
        except Exception as exc:  # noqa: BLE001 - fall back to no-op on metrics setup failure.
            self.enabled = False
            LOGGER.warning("cloudwatch_metric_client_init_failed", error=str(exc))
            return None

    @staticmethod
    def _base_dimensions(environment: str, version: str, hostname: str) -> list[dict[str, str]]:
        return [
            {"Name": "Environment", "Value": environment},
            {"Name": "Version", "Value": version},
            {"Name": "Hostname", "Value": hostname},
        ]

    @staticmethod
    def _cloudwatch_unit(unit: str) -> str:
        if unit == "Ratio":
            return "None"
        return unit

    @staticmethod
    def _metric_name(name: str) -> str:
        return "".join(part.capitalize() for part in name.split("_") if part)

    @staticmethod
    def _timestamp(value: str) -> datetime | str:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
