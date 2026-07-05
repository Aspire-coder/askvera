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


def _failed_request_metric() -> RequestMetric:
    return RequestMetric(
        method="POST",
        path="/api/chat",
        status_code=500,
        duration_ms=30.0,
        success=False,
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
    assert CLOUDWATCH_METRIC_NAMES["total_requests"] == "TotalRequests"
    assert CLOUDWATCH_METRIC_NAMES["successful_requests"] == "SuccessfulRequests"
    assert CLOUDWATCH_METRIC_NAMES["failed_requests"] == "FailedRequests"
    assert CLOUDWATCH_METRIC_NAMES["average_request_duration"] == "AverageRequestDuration"
    assert CLOUDWATCH_METRIC_NAMES["governance"] == "GovernanceLatency"
    assert CLOUDWATCH_METRIC_NAMES["retrieval"] == "RetrievalLatency"
    assert CLOUDWATCH_METRIC_NAMES["prompt_build"] == "PromptBuildLatency"
    assert CLOUDWATCH_METRIC_NAMES["model_generate"] == "ModelLatency"
    assert CLOUDWATCH_METRIC_NAMES["validation"] == "ValidationLatency"
    assert CLOUDWATCH_METRIC_NAMES["response_build"] == "ResponseBuildLatency"
    assert CLOUDWATCH_METRIC_NAMES["cache_hit_ratio"] == "CacheHitRatio"
    assert CLOUDWATCH_METRIC_NAMES["audit_queue_depth"] == "AuditQueueDepth"
    assert CLOUDWATCH_METRIC_NAMES["retrieval_health"] == "RetrievalHealth"
    assert CLOUDWATCH_METRIC_NAMES["governance_health"] == "GovernanceHealth"
    assert CLOUDWATCH_METRIC_NAMES["validation_health"] == "ValidationHealth"


def test_cloudwatch_provider_discards_when_disabled() -> None:
    client = FakeCloudWatchClient()
    provider = CloudWatchMetricsProvider(client=client, enabled=False, batch_size=1)

    provider.publish_system(SystemMetric(name="audit_queue_depth", value=3, unit="Count"))
    provider.flush()

    assert client.calls == []


def test_cloudwatch_provider_publishes_request_metrics() -> None:
    client = FakeCloudWatchClient()
    provider = CloudWatchMetricsProvider(client=client, enabled=True, namespace="ASKVeraTest", batch_size=5)

    provider.publish_request(_request_metric(), RequestMetricSnapshot(1, 1, 0, 12.5, 12.5))

    assert len(client.calls) == 1
    assert client.calls[0]["Namespace"] == "ASKVeraTest"
    assert [metric["MetricName"] for metric in client.calls[0]["MetricData"]] == [
        "RequestCount",
        "RequestDuration",
        "TotalRequests",
        "SuccessfulRequests",
        "AverageRequestDuration",
    ]


def test_cloudwatch_provider_publishes_failed_request_aggregate() -> None:
    client = FakeCloudWatchClient()
    provider = CloudWatchMetricsProvider(client=client, enabled=True, namespace="ASKVeraTest", batch_size=5)

    provider.publish_request(_failed_request_metric(), RequestMetricSnapshot(1, 0, 1, 30.0, 30.0))

    metric_names = [metric["MetricName"] for metric in client.calls[0]["MetricData"]]
    assert "TotalRequests" in metric_names
    assert "FailedRequests" in metric_names
    assert "SuccessfulRequests" not in metric_names
    assert "AverageRequestDuration" in metric_names


def test_cloudwatch_provider_publishes_pipeline_and_system_metrics() -> None:
    client = FakeCloudWatchClient()
    provider = CloudWatchMetricsProvider(client=client, enabled=True, namespace="ASKVeraTest", batch_size=4)

    provider.publish_pipeline(_pipeline_metric("model_generate"), None)
    provider.publish_system(SystemMetric(name="cache_hit_ratio", value=0.82, unit="Ratio"))

    assert len(client.calls) == 1
    metric_data = client.calls[0]["MetricData"]
    assert metric_data[0]["MetricName"] == "ModelLatency"
    assert metric_data[0]["Unit"] == "Milliseconds"
    assert metric_data[1]["MetricName"] == "ModelLatency"
    assert metric_data[1]["Dimensions"] == [
        {"Name": "Environment", "Value": metric_data[1]["Dimensions"][0]["Value"]},
        {"Name": "Version", "Value": metric_data[1]["Dimensions"][1]["Value"]},
    ]
    assert metric_data[2]["MetricName"] == "CacheHitRatio"
    assert metric_data[2]["Unit"] == "None"
    assert metric_data[3]["MetricName"] == "CacheHitRatio"
    assert metric_data[3]["Unit"] == "None"


def test_cloudwatch_provider_publishes_all_aggregate_pipeline_stage_metrics() -> None:
    client = FakeCloudWatchClient()
    provider = CloudWatchMetricsProvider(client=client, enabled=True, namespace="ASKVeraTest", batch_size=12)

    for stage in ("governance", "retrieval", "prompt_build", "model_generate", "validation", "response_build"):
        provider.publish_pipeline(_pipeline_metric(stage), None)

    metric_names = [metric["MetricName"] for metric in client.calls[0]["MetricData"]]
    assert metric_names.count("GovernanceLatency") == 2
    assert metric_names.count("RetrievalLatency") == 2
    assert metric_names.count("PromptBuildLatency") == 2
    assert metric_names.count("ModelLatency") == 2
    assert metric_names.count("ValidationLatency") == 2
    assert metric_names.count("ResponseBuildLatency") == 2


def test_cloudwatch_provider_publishes_aggregate_health_metrics() -> None:
    client = FakeCloudWatchClient()
    provider = CloudWatchMetricsProvider(client=client, enabled=True, namespace="ASKVeraTest", batch_size=8)

    provider.publish_system(SystemMetric(name="audit_queue_depth", value=3, unit="Count"))
    provider.publish_system(SystemMetric(name="retrieval_health", value=1, unit="None"))
    provider.publish_system(SystemMetric(name="governance_health", value=1, unit="None"))
    provider.publish_system(SystemMetric(name="validation_health", value=1, unit="None"))

    metric_names = [metric["MetricName"] for metric in client.calls[0]["MetricData"]]
    assert metric_names.count("AuditQueueDepth") == 2
    assert metric_names.count("RetrievalHealth") == 2
    assert metric_names.count("GovernanceHealth") == 2
    assert metric_names.count("ValidationHealth") == 2


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
