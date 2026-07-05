"""Unit tests for request metrics collection."""

from app.metrics import MetricsCollector, RequestMetric


def _metric(status_code: int, duration_ms: float) -> RequestMetric:
    return RequestMetric(
        method="GET",
        path="/health",
        status_code=status_code,
        duration_ms=duration_ms,
        success=status_code < 400,
        correlation_id="cid",
    )


def test_metrics_collector_tracks_request_counts() -> None:
    collector = MetricsCollector()

    collector.record_request(_metric(200, 10.0))
    snapshot = collector.record_request(_metric(500, 30.0))

    assert snapshot.request_count == 2
    assert snapshot.success_count == 1
    assert snapshot.failure_count == 1
    assert snapshot.total_duration_ms == 40.0
    assert snapshot.average_duration_ms == 20.0


def test_metrics_collector_starts_empty() -> None:
    snapshot = MetricsCollector().snapshot()

    assert snapshot.request_count == 0
    assert snapshot.success_count == 0
    assert snapshot.failure_count == 0
    assert snapshot.average_duration_ms == 0.0
