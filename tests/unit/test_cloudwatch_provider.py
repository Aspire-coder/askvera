"""Unit tests for CloudWatch metrics provider."""

from app.metrics.models import PipelineMetric, RequestMetric, RequestMetricSnapshot, SystemMetric
from app.metrics.providers.cloudwatch_provider import CLOUDWATCH_METRIC_NAMES, CloudWatchMetricsProvider
from app.metrics.registry import metrics_registry
from config import settings


class FakeCloudWatchClient:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls = []

    def put_metric_data(self, **kwargs) -> None:
        if self.fail:
            raise RuntimeError("cloudwatch unavailable")
        self.calls.append(kwargs)


def _request_metric() -> RequestMetric:
    return RequestMetric(
        method="GET",
        path="/health",
        status_code=200,
        duration_ms=12.5,
        success=True,
        correlation_id="cid",
    )


def _pipeline_metric(stage: str = "retrieval") -> PipelineMetric:
    return PipelineMetric(stage=stage, duration_ms=25.0, success=True, correlation_id="cid")


def test_cloudwatch_provider_can_initialize_disabled() -> None:
    provider = CloudWatchMetricsProvider(enabled=False)

    assert provider.name == "cloudwatch"
    assert provider.enabled is False
    assert provider.client is None


def test_cloudwatch_metric_mapping_is_stable() -> None:
    assert CLOUDWATCH_METRIC_NAMES["request_count"] == "RequestCount"
    assert CLOUDWATCH_METRIC_NAMES["request_duration"] == "RequestDuration"
    assert CLOUDWATCH_METRIC_NAMES["governance"] == "GovernanceLatency"
    assert CLOUDWATCH_METRIC_NAMES["retrieval"] == "RetrievalLatency"
    assert CLOUDWATCH_METRIC_NAMES["prompt_build"] == "PromptBuildLatency"
    assert CLOUDWATCH_METRIC_NAMES["model_generate"] == "ModelLatency"
    assert CLOUDWATCH_METRIC_NAMES["validation"] == "ValidationLatency"
    assert CLOUDWATCH_METRIC_NAMES["response_build"] == "ResponseBuildLatency"
    assert CLOUDWATCH_METRIC_NAMES["cache_hit_ratio"] == "CacheHitRatio"
    assert CLOUDWATCH_METRIC_NAMES["audit_queue_depth"] == "AuditQueueDepth"


def test_cloudwatch_provider_discards_when_disabled() -> None:
    client = FakeCloudWatchClient()
    provider = CloudWatchMetricsProvider(client=client, enabled=False, batch_size=1)

    provider.publish_system(SystemMetric(name="audit_queue_depth", value=3, unit="Count"))
    provider.flush()

    assert client.calls == []


def test_cloudwatch_provider_publishes_request_metrics() -> None:
    client = FakeCloudWatchClient()
    provider = CloudWatchMetricsProvider(client=client, enabled=True, namespace="ASKVeraTest", batch_size=2)

    provider.publish_request(_request_metric(), RequestMetricSnapshot(1, 1, 0, 12.5, 12.5))

    assert len(client.calls) == 1
    assert client.calls[0]["Namespace"] == "ASKVeraTest"
    assert [metric["MetricName"] for metric in client.calls[0]["MetricData"]] == [
        "RequestCount",
        "RequestDuration",
    ]


def test_cloudwatch_provider_publishes_pipeline_and_system_metrics() -> None:
    client = FakeCloudWatchClient()
    provider = CloudWatchMetricsProvider(client=client, enabled=True, namespace="ASKVeraTest", batch_size=2)

    provider.publish_pipeline(_pipeline_metric("model_generate"), None)
    provider.publish_system(SystemMetric(name="cache_hit_ratio", value=0.82, unit="Ratio"))

    assert len(client.calls) == 1
    metric_data = client.calls[0]["MetricData"]
    assert metric_data[0]["MetricName"] == "ModelLatency"
    assert metric_data[0]["Unit"] == "Milliseconds"
    assert metric_data[1]["MetricName"] == "CacheHitRatio"
    assert metric_data[1]["Unit"] == "None"


def test_cloudwatch_provider_failure_does_not_raise() -> None:
    client = FakeCloudWatchClient(fail=True)
    provider = CloudWatchMetricsProvider(client=client, enabled=True, namespace="ASKVeraTest", batch_size=1)

    provider.publish_system(SystemMetric(name="audit_queue_depth", value=3, unit="Count"))
    provider.flush()


def test_cloudwatch_provider_is_registered() -> None:
    assert metrics_registry.get("cloudwatch").name == "cloudwatch"


def test_cloudwatch_configuration_defaults_exist() -> None:
    assert isinstance(settings.ENABLE_METRICS, bool)
    assert settings.METRICS_PROVIDER
    assert isinstance(settings.ENABLE_CLOUDWATCH_METRICS, bool)
    assert settings.CLOUDWATCH_NAMESPACE
    assert settings.CLOUDWATCH_BATCH_SIZE > 0
    assert settings.CLOUDWATCH_FLUSH_INTERVAL > 0
