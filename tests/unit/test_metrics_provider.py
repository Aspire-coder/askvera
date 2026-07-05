"""Unit tests for metrics providers and publisher behavior."""

from app.metrics import MetricsPublisher, PipelineMetric, RequestMetric
from app.metrics.collector import MetricsCollector
from app.metrics.models import PipelineStageSnapshot, RequestMetricSnapshot
from app.metrics.providers import NullMetricsProvider
from app.metrics.registry import MetricsRegistry


class RecordingProvider:
    name = "recording"

    def __init__(self) -> None:
        self.requests = []
        self.pipelines = []
        self.flushed = False

    def publish_request(self, metric, snapshot) -> None:
        self.requests.append((metric, snapshot))

    def publish_pipeline(self, metric, snapshot) -> None:
        self.pipelines.append((metric, snapshot))

    def flush(self) -> None:
        self.flushed = True


def _request_metric() -> RequestMetric:
    return RequestMetric(
        method="GET",
        path="/health",
        status_code=200,
        duration_ms=10.0,
        success=True,
        correlation_id="cid",
    )


def _pipeline_metric() -> PipelineMetric:
    return PipelineMetric(stage="retrieval", duration_ms=10.0, success=True, correlation_id="cid")


def test_null_metrics_provider_discards_metrics() -> None:
    provider = NullMetricsProvider()

    provider.publish_request(_request_metric(), RequestMetricSnapshot(1, 1, 0, 10.0, 10.0))
    provider.publish_pipeline(_pipeline_metric(), PipelineStageSnapshot("retrieval", 1, 10.0, 10.0, 10.0, 10.0))
    provider.flush()

    assert provider.name == "null"


def test_metrics_publisher_uses_configured_provider() -> None:
    registry = MetricsRegistry()
    provider = RecordingProvider()
    registry.register(provider)
    publisher = MetricsPublisher(registry=registry, provider_name="recording", enabled=True)

    publisher.publish_request(_request_metric(), RequestMetricSnapshot(1, 1, 0, 10.0, 10.0))
    publisher.publish_pipeline(_pipeline_metric(), PipelineStageSnapshot("retrieval", 1, 10.0, 10.0, 10.0, 10.0))
    publisher.flush()

    assert len(provider.requests) == 1
    assert len(provider.pipelines) == 1
    assert provider.flushed is True


def test_metrics_publisher_respects_disabled_metrics() -> None:
    registry = MetricsRegistry()
    provider = RecordingProvider()
    registry.register(provider)
    publisher = MetricsPublisher(registry=registry, provider_name="recording", enabled=False)

    publisher.publish_request(_request_metric(), RequestMetricSnapshot(1, 1, 0, 10.0, 10.0))
    publisher.publish_pipeline(_pipeline_metric(), PipelineStageSnapshot("retrieval", 1, 10.0, 10.0, 10.0, 10.0))
    publisher.flush()

    assert provider.requests == []
    assert provider.pipelines == []
    assert provider.flushed is False


def test_metrics_collector_reset_clears_snapshots() -> None:
    collector = MetricsCollector()
    collector.record_request(_request_metric())
    collector.record_pipeline(_pipeline_metric())

    collector.reset()

    assert collector.snapshot().request_count == 0
    assert collector.pipeline_snapshot("retrieval").count == 0
