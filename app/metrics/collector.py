"""In-process metrics collector."""

from threading import Lock

from .models import PipelineMetric, PipelineStageSnapshot, RequestMetric, RequestMetricSnapshot


class MetricsCollector:
    """Collect lightweight request metrics in memory."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._request_count = 0
        self._success_count = 0
        self._failure_count = 0
        self._total_duration_ms = 0.0
        self._stage_metrics: dict[str, dict[str, float | int]] = {}

    def record_request(self, metric: RequestMetric) -> RequestMetricSnapshot:
        """Record one request metric and return the current snapshot."""
        with self._lock:
            self._request_count += 1
            if metric.success:
                self._success_count += 1
            else:
                self._failure_count += 1
            self._total_duration_ms += metric.duration_ms
            return self.snapshot()

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

    def snapshot(self) -> RequestMetricSnapshot:
        """Return current in-memory request metrics."""
        average_duration = self._total_duration_ms / self._request_count if self._request_count else 0.0
        return RequestMetricSnapshot(
            request_count=self._request_count,
            success_count=self._success_count,
            failure_count=self._failure_count,
            total_duration_ms=round(self._total_duration_ms, 2),
            average_duration_ms=round(average_duration, 2),
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


metrics_collector = MetricsCollector()
