"""Health metrics must actually be published, not merely recordable.

MetricsCollector carried recorders for governance, validation and cache health
since the monitoring work landed, and CloudWatch carried alarms watching the
metrics they produce. Nothing in the application ever called them, so
GovernanceHealth, ValidationHealth and CacheHitRatio had no data. Every one of
those alarms uses treat_missing_data="notBreaching", so they sat in OK forever
and looked like health rather than absence.

These tests assert the wiring exists, which is the part that was missing.
"""

from app.metrics import health as health_metrics
from app.metrics.models import SystemMetric


class RecordingPublisher:
    def __init__(self) -> None:
        self.metrics: list[SystemMetric] = []

    def publish_system(self, metric: SystemMetric) -> None:
        self.metrics.append(metric)


def _capture(monkeypatch) -> RecordingPublisher:
    publisher = RecordingPublisher()
    monkeypatch.setattr(health_metrics, "metrics_publisher", publisher)
    return publisher


def _values(publisher: RecordingPublisher, name: str) -> list[float]:
    return [metric.value for metric in publisher.metrics if metric.name == name]


def test_governance_allow_publishes_healthy(monkeypatch):
    publisher = _capture(monkeypatch)
    health_metrics.record_governance_outcome(allowed=True)
    assert _values(publisher, "governance_health") == [1.0]


def test_governance_provider_failure_publishes_unhealthy(monkeypatch):
    publisher = _capture(monkeypatch)
    health_metrics.record_governance_outcome(allowed=False, provider_failed=True)
    assert _values(publisher, "governance_health") == [0.0]


def test_a_refusal_does_not_count_against_governance_health(monkeypatch):
    """Blocking an income claim is the system working, not a health problem."""
    publisher = _capture(monkeypatch)
    health_metrics.record_governance_outcome(allowed=False, provider_failed=False)
    assert _values(publisher, "governance_health") == []


def test_validation_outcomes_publish_both_ways(monkeypatch):
    publisher = _capture(monkeypatch)
    health_metrics.record_validation_outcome(has_critical=False)
    health_metrics.record_validation_outcome(has_critical=True)
    assert _values(publisher, "validation_health") == [1.0, 0.0]


def test_cache_outcomes_publish_a_ratio(monkeypatch):
    publisher = _capture(monkeypatch)
    health_metrics.record_cache_outcome(hit=True)
    health_metrics.record_cache_outcome(hit=False)
    ratios = _values(publisher, "cache_hit_ratio")
    assert len(ratios) == 2
    assert all(0.0 <= ratio <= 1.0 for ratio in ratios)


def test_retrieval_outcomes_publish_both_ways(monkeypatch):
    """Failure alone would latch the gauge at 0.0 and never let the alarm clear."""
    publisher = _capture(monkeypatch)
    health_metrics.record_retrieval_outcome(success=False)
    health_metrics.record_retrieval_outcome(success=True)
    assert _values(publisher, "retrieval_health") == [0.0, 1.0]


def test_a_publisher_failure_never_reaches_the_caller(monkeypatch):
    class BrokenPublisher:
        def publish_system(self, metric: SystemMetric) -> None:
            raise RuntimeError("cloudwatch unavailable")

    monkeypatch.setattr(health_metrics, "metrics_publisher", BrokenPublisher())
    health_metrics.record_governance_outcome(allowed=True)
    health_metrics.record_validation_outcome(has_critical=True)
    health_metrics.record_cache_outcome(hit=True)


def test_governance_engine_records_its_outcome(monkeypatch):
    """The wiring, not the helper: this is what was absent."""
    from app.governance import engine as governance_engine_module

    calls: list[dict] = []
    monkeypatch.setattr(
        governance_engine_module,
        "record_governance_outcome",
        lambda **kwargs: calls.append(kwargs),
    )

    engine = governance_engine_module.GovernanceEngine()
    engine.evaluate(text="What is a Case Credit?", country="US", language="en", correlation_id="cid")

    assert calls, "governance evaluate must record an outcome"
    assert set(calls[0]) == {"allowed", "provider_failed"}


def test_cache_read_records_hit_and_miss(monkeypatch):
    import services.cache as cache_service

    calls: list[dict] = []
    monkeypatch.setattr(cache_service, "record_cache_outcome", lambda **kwargs: calls.append(kwargs))

    class FakeRedis:
        def __init__(self, value):
            self.value = value

        def get(self, key):
            return self.value

    monkeypatch.setattr(cache_service, "_redis_client", FakeRedis(b'{"response": "x"}'))
    cache_service.get_cache_value("k", "cid")
    monkeypatch.setattr(cache_service, "_redis_client", FakeRedis(None))
    cache_service.get_cache_value("k", "cid")

    assert [call["hit"] for call in calls] == [True, False]


def test_an_unreachable_cache_is_not_recorded_as_a_miss(monkeypatch):
    """A connectivity failure would otherwise drag the ratio down misleadingly."""
    import redis

    import services.cache as cache_service

    calls: list[dict] = []
    monkeypatch.setattr(cache_service, "record_cache_outcome", lambda **kwargs: calls.append(kwargs))

    class BrokenRedis:
        def get(self, key):
            raise redis.RedisError("unreachable")

    monkeypatch.setattr(cache_service, "_redis_client", BrokenRedis())
    assert cache_service.get_cache_value("k", "cid") is None
    assert calls == []


def test_audit_queue_depth_is_published(monkeypatch):
    publisher = _capture(monkeypatch)
    health_metrics.record_audit_queue_depth(7)
    assert _values(publisher, "audit_queue_depth") == [7.0]


def test_audit_publisher_samples_depth_on_enqueue(monkeypatch):
    """The wiring: AuditQueueDepth had no producer at all."""
    import asyncio

    from app.audit import publisher as audit_publisher_module

    depths: list[int] = []
    monkeypatch.setattr(audit_publisher_module, "record_audit_queue_depth", depths.append)

    class FakeQueue:
        def put_nowait(self, event):
            return None

    monkeypatch.setattr(audit_publisher_module, "audit_queue", FakeQueue())
    monkeypatch.setattr(audit_publisher_module, "queue_size", lambda: 3)

    asyncio.run(audit_publisher_module.AuditPublisher().publish(object()))

    assert depths == [3]
