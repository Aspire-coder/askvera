"""In-process metrics collector."""

from threading import Lock

from .models import RequestMetric, RequestMetricSnapshot


class MetricsCollector:
    """Collect lightweight request metrics in memory."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._request_count = 0
        self._success_count = 0
        self._failure_count = 0
        self._total_duration_ms = 0.0

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


metrics_collector = MetricsCollector()
