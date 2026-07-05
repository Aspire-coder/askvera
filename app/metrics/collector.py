"""In-process metrics collector."""

from threading import RLock

from .models import (
    HealthSummary,
    MetricsSnapshot,
    PipelineMetric,
    PipelineStageSnapshot,
    RequestMetric,
    RequestMetricSnapshot,
    SystemMetric,
)


class MetricsCollector:
    """Collect lightweight request metrics in memory."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._request_count = 0
        self._success_count = 0
        self._failure_count = 0
        self._total_duration_ms = 0.0
        self._stage_metrics: dict[str, dict[str, float | int]] = {}
        self._system_metrics: dict[str, SystemMetric] = {}

    def record_request(self, metric: RequestMetric) -> RequestMetricSnapshot:
        """Record one request metric and return the current snapshot."""
        with self._lock:
            self._request_count += 1
            if metric.success:
                self._success_count += 1
            else:
                self._failure_count += 1
            self._total_duration_ms += metric.duration_ms
            return self.request_snapshot()

    def record_pipeline(self, metric: PipelineMetric) -> PipelineStageSnapshot:
        """Record one pipeline stage metric and return that stage snapshot."""
        with self._lock:
            stage = self._stage_metrics.setdefault(
                metric.stage,
                {
                    "count": 0,
                    "total_duration_ms": 0.0,
                    "min_duration_ms": metric.duration_ms,
                    "max_duration_ms": metric.duration_ms,
                },
            )
            stage["count"] = int(stage["count"]) + 1
            stage["total_duration_ms"] = float(stage["total_duration_ms"]) + metric.duration_ms
            stage["min_duration_ms"] = min(float(stage["min_duration_ms"]), metric.duration_ms)
            stage["max_duration_ms"] = max(float(stage["max_duration_ms"]), metric.duration_ms)
            return self.pipeline_snapshot(metric.stage)

    def record_system(self, metric: SystemMetric) -> SystemMetric:
        """Record one system metric sample."""
        with self._lock:
            self._system_metrics[metric.name] = metric
            return metric

    def increment_system_metric(self, name: str, amount: float = 1.0, unit: str = "Count") -> SystemMetric:
        """Increment a numeric system metric by name."""
        current = self._system_metrics.get(name)
        current_value = current.value if current else 0.0
        return self.record_system(SystemMetric(name=name, value=current_value + amount, unit=unit))

    def record_cache_hit(self) -> None:
        """Track one cache hit and update cache hit ratio."""
        self.increment_system_metric("cache_hits")
        self._update_cache_hit_ratio()

    def record_cache_miss(self) -> None:
        """Track one cache miss and update cache hit ratio."""
        self.increment_system_metric("cache_misses")
        self._update_cache_hit_ratio()

    def record_retrieval_failure(self) -> None:
        """Track one retrieval failure."""
        self.increment_system_metric("retrieval_failures")

    def record_low_confidence(self) -> None:
        """Track one low-confidence retrieval/model outcome."""
        self.increment_system_metric("low_confidence")

    def record_empty_retrieval(self) -> None:
        """Track one empty retrieval result."""
        self.increment_system_metric("empty_retrievals")

    def record_governance_allow(self) -> None:
        """Track one governance allow decision."""
        self.increment_system_metric("governance_allows")

    def record_governance_block(self) -> None:
        """Track one governance block decision."""
        self.increment_system_metric("governance_blocks")

    def record_governance_critical(self) -> None:
        """Track one critical governance decision."""
        self.increment_system_metric("governance_critical")

    def record_governance_provider_failure(self) -> None:
        """Track one governance provider failure."""
        self.increment_system_metric("governance_provider_failures")

    def record_validation_passed(self) -> None:
        """Track one passed validation."""
        self.increment_system_metric("validation_passed")

    def record_validation_warning(self) -> None:
        """Track one warning validation result."""
        self.increment_system_metric("validation_warnings")

    def record_validation_critical(self) -> None:
        """Track one critical validation result."""
        self.increment_system_metric("validation_critical")

    def record_audit_queue_depth(self, depth: int) -> None:
        """Track current audit queue depth."""
        self.record_system(SystemMetric(name="audit_queue_depth", value=float(depth), unit="Count"))

    def reset(self) -> None:
        """Reset all in-memory counters and stage timing aggregates."""
        with self._lock:
            self._request_count = 0
            self._success_count = 0
            self._failure_count = 0
            self._total_duration_ms = 0.0
            self._stage_metrics.clear()
            self._system_metrics.clear()

    def request_snapshot(self) -> RequestMetricSnapshot:
        """Return current in-memory request metrics."""
        average_duration = self._total_duration_ms / self._request_count if self._request_count else 0.0
        return RequestMetricSnapshot(
            request_count=self._request_count,
            success_count=self._success_count,
            failure_count=self._failure_count,
            total_duration_ms=round(self._total_duration_ms, 2),
            average_duration_ms=round(average_duration, 2),
        )

    def snapshot(self) -> MetricsSnapshot:
        """Return a full in-memory metrics snapshot."""
        with self._lock:
            return MetricsSnapshot(
                request=self.request_snapshot(),
                pipeline={
                    stage_name: self.pipeline_snapshot(stage_name)
                    for stage_name in sorted(self._stage_metrics)
                },
                system=dict(self._system_metrics),
            )

    def pipeline_snapshot(self, stage_name: str) -> PipelineStageSnapshot:
        """Return current in-memory timing metrics for one stage."""
        stage = self._stage_metrics.get(stage_name)
        if not stage:
            return PipelineStageSnapshot(
                stage=stage_name,
                count=0,
                total_duration_ms=0.0,
                average_duration_ms=0.0,
                min_duration_ms=0.0,
                max_duration_ms=0.0,
            )
        count = int(stage["count"])
        total = float(stage["total_duration_ms"])
        average = total / count if count else 0.0
        return PipelineStageSnapshot(
            stage=stage_name,
            count=count,
            total_duration_ms=round(total, 2),
            average_duration_ms=round(average, 2),
            min_duration_ms=round(float(stage["min_duration_ms"]), 2),
            max_duration_ms=round(float(stage["max_duration_ms"]), 2),
        )

    def system_snapshot(self, name: str) -> SystemMetric | None:
        """Return the latest system metric for one metric name."""
        return self._system_metrics.get(name)

    def health_summary(self) -> HealthSummary:
        """Return compact health summary metrics."""
        cache_hit_ratio = self._system_value("cache_hit_ratio")
        retrieval_failures = self._system_value("retrieval_failures")
        request_count = max(self._request_count, 1)
        validation_failures = int(self._system_value("validation_critical"))
        status = "healthy" if validation_failures == 0 else "degraded"
        return HealthSummary(
            status=status,
            cache_hit_ratio=round(cache_hit_ratio, 4),
            retrieval_failure_rate=round(retrieval_failures / request_count, 4),
            governance_blocks=int(self._system_value("governance_blocks")),
            validation_failures=validation_failures,
            audit_queue_depth=int(self._system_value("audit_queue_depth")),
        )

    def _system_value(self, name: str) -> float:
        metric = self._system_metrics.get(name)
        return metric.value if metric else 0.0

    def _update_cache_hit_ratio(self) -> None:
        hits = self._system_value("cache_hits")
        misses = self._system_value("cache_misses")
        total = hits + misses
        ratio = hits / total if total else 0.0
        self.record_system(SystemMetric(name="cache_hit_ratio", value=round(ratio, 4), unit="Ratio"))


metrics_collector = MetricsCollector()
