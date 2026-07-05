"""Unit tests for system health metrics."""

from app.metrics import MetricsCollector, PipelineMetric, RequestMetric, SystemMetric


def _request_metric(status_code: int = 200) -> RequestMetric:
    return RequestMetric(
        method="POST",
        path="/api/chat",
        status_code=status_code,
        duration_ms=25.0,
        success=status_code < 400,
        correlation_id="cid",
    )


def _pipeline_metric() -> PipelineMetric:
    return PipelineMetric(stage="model_generate", duration_ms=120.0, success=True, correlation_id="cid")


def test_cache_hit_ratio_calculation() -> None:
    collector = MetricsCollector()

    collector.record_cache_hit()
    collector.record_cache_miss()
    collector.record_cache_hit()

    assert collector.system_snapshot("cache_hits").value == 2.0
    assert collector.system_snapshot("cache_misses").value == 1.0
    assert collector.system_snapshot("cache_hit_ratio").value == 0.6667


def test_system_metric_recording() -> None:
    collector = MetricsCollector()

    collector.record_system(SystemMetric(name="active_sessions", value=52, unit="Count"))

    metric = collector.system_snapshot("active_sessions")
    assert metric is not None
    assert metric.name == "active_sessions"
    assert metric.value == 52
    assert metric.unit == "Count"


def test_full_snapshot_includes_request_pipeline_and_system_metrics() -> None:
    collector = MetricsCollector()
    collector.record_request(_request_metric())
    collector.record_pipeline(_pipeline_metric())
    collector.record_system(SystemMetric(name="audit_queue_depth", value=7, unit="Count"))

    snapshot = collector.snapshot()

    assert snapshot.request.request_count == 1
    assert snapshot.pipeline["model_generate"].count == 1
    assert snapshot.system["audit_queue_depth"].value == 7


def test_health_summary_generation() -> None:
    collector = MetricsCollector()
    collector.record_request(_request_metric())
    collector.record_request(_request_metric())
    collector.record_cache_hit()
    collector.record_cache_miss()
    collector.record_cache_hit()
    collector.record_retrieval_failure()
    collector.record_governance_block()
    collector.record_validation_critical()
    collector.record_audit_queue_depth(12)

    summary = collector.health_summary()

    assert summary.status == "degraded"
    assert summary.cache_hit_ratio == 0.6667
    assert summary.retrieval_failure_rate == 0.5
    assert summary.governance_blocks == 1
    assert summary.validation_failures == 1
    assert summary.audit_queue_depth == 12


def test_reset_clears_system_metrics() -> None:
    collector = MetricsCollector()
    collector.record_request(_request_metric())
    collector.record_cache_hit()
    collector.record_retrieval_failure()
    collector.record_governance_block()
    collector.record_validation_critical()
    collector.record_audit_queue_depth(5)

    collector.reset()
    snapshot = collector.snapshot()
    summary = collector.health_summary()

    assert snapshot.request.request_count == 0
    assert snapshot.system == {}
    assert summary.status == "healthy"
    assert summary.cache_hit_ratio == 0.0
    assert summary.retrieval_failure_rate == 0.0
    assert summary.governance_blocks == 0
    assert summary.validation_failures == 0
    assert summary.audit_queue_depth == 0
