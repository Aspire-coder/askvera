"""Unit tests for delivered-response and fallback metrics."""

from app.metrics import responses as response_metrics
from app.metrics.models import SystemMetric
from app.metrics.names import (
    DELIVERED_RESPONSES_METRIC,
    FALLBACK_BY_LAYER_METRIC,
    FALLBACK_RESPONSES_METRIC,
)
from app.metrics.providers.cloudwatch_provider import CloudWatchMetricsProvider
from app.monitoring.alarms import ALARM_NAMES, build_alarm_definitions


class RecordingPublisher:
    def __init__(self) -> None:
        self.metrics: list[SystemMetric] = []

    def publish_system(self, metric: SystemMetric) -> None:
        self.metrics.append(metric)


def _capture(monkeypatch) -> RecordingPublisher:
    publisher = RecordingPublisher()
    monkeypatch.setattr(response_metrics, "metrics_publisher", publisher)
    return publisher


def _by_name(publisher: RecordingPublisher) -> dict[str, SystemMetric]:
    return {metric.name: metric for metric in publisher.metrics}


def test_grounded_answer_counts_as_delivered_and_not_fallback(monkeypatch):
    publisher = _capture(monkeypatch)

    response_metrics.record_delivered_response({"fallback": False})

    recorded = _by_name(publisher)
    assert recorded["delivered_responses"].value == 1.0
    # Zero rather than absent: the average of this metric is the fallback rate,
    # which requires successful answers to be counted as 0.0 samples.
    assert recorded["fallback_responses"].value == 0.0
    assert "fallback_by_layer" not in recorded


def test_fallback_counts_and_carries_its_failure_layer(monkeypatch):
    publisher = _capture(monkeypatch)

    response_metrics.record_delivered_response({"fallback": True, "failure_layer": "evidence_gate"})

    recorded = _by_name(publisher)
    assert recorded["delivered_responses"].value == 1.0
    assert recorded["fallback_responses"].value == 1.0
    assert recorded["fallback_by_layer"].value == 1.0
    assert recorded["fallback_by_layer"].metadata == {"failure_layer": "evidence_gate"}


def test_fallback_without_a_layer_is_still_counted_by_layer(monkeypatch):
    """A missing label must not make a fallback vanish from the breakdown."""
    publisher = _capture(monkeypatch)

    response_metrics.record_delivered_response({"fallback": True})

    recorded = _by_name(publisher)
    assert recorded["fallback_by_layer"].metadata == {"failure_layer": response_metrics.UNLABELLED_LAYER}


def test_missing_metadata_is_treated_as_a_delivered_answer(monkeypatch):
    publisher = _capture(monkeypatch)

    response_metrics.record_delivered_response(None)

    recorded = _by_name(publisher)
    assert recorded["delivered_responses"].value == 1.0
    assert recorded["fallback_responses"].value == 0.0


def test_metric_failure_never_propagates_to_the_caller(monkeypatch):
    """A delivered answer must not become an error because counting it failed."""

    class BrokenPublisher:
        def publish_system(self, metric: SystemMetric) -> None:
            raise RuntimeError("cloudwatch unavailable")

    monkeypatch.setattr(response_metrics, "metrics_publisher", BrokenPublisher())

    response_metrics.record_delivered_response({"fallback": True, "failure_layer": "evidence_gate"})


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def put_metric_data(self, **kwargs) -> None:
        self.calls.append(kwargs)


def _queued(client: FakeClient) -> list[dict]:
    return [item for call in client.calls for item in call["MetricData"]]


def test_failure_layer_becomes_a_cloudwatch_dimension():
    client = FakeClient()
    provider = CloudWatchMetricsProvider(client=client, enabled=True)

    provider.publish_system(
        SystemMetric(
            name="fallback_by_layer",
            value=1.0,
            unit="Count",
            metadata={"failure_layer": "evidence_gate"},
        )
    )
    provider.flush()

    dimension_sets = [
        {dimension["Name"]: dimension["Value"] for dimension in item["Dimensions"]}
        for item in _queued(client)
        if item["MetricName"] == FALLBACK_BY_LAYER_METRIC
    ]
    assert dimension_sets, "expected the by-layer metric to be queued"
    assert all(entry.get("FailureLayer") == "evidence_gate" for entry in dimension_sets)


def test_blank_failure_layer_falls_back_to_a_non_empty_dimension_value():
    """CloudWatch rejects empty dimension values, so a blank must be substituted."""
    client = FakeClient()
    provider = CloudWatchMetricsProvider(client=client, enabled=True)

    provider.publish_system(
        SystemMetric(name="fallback_by_layer", value=1.0, unit="Count", metadata={"failure_layer": "  "})
    )
    provider.flush()

    values = [
        dimension["Value"]
        for item in _queued(client)
        for dimension in item["Dimensions"]
        if dimension["Name"] == "FailureLayer"
    ]
    assert values and all(value.strip() for value in values)


def test_metrics_without_a_dimension_mapping_are_unchanged():
    client = FakeClient()
    provider = CloudWatchMetricsProvider(client=client, enabled=True)

    provider.publish_system(SystemMetric(name="fallback_responses", value=0.0, unit="None"))
    provider.flush()

    for item in _queued(client):
        assert all(dimension["Name"] != "FailureLayer" for dimension in item["Dimensions"])


def test_pending_metrics_flush_once_the_interval_has_elapsed(monkeypatch):
    """A partial batch must not sit unsent through a quiet period."""
    client = FakeClient()
    provider = CloudWatchMetricsProvider(client=client, enabled=True, batch_size=1000)
    provider.flush_interval = 30

    provider.publish_system(SystemMetric(name="fallback_responses", value=0.0, unit="None"))
    assert client.calls == [], "one metric should not reach a batch size of 1000"

    monkeypatch.setattr(
        "app.metrics.providers.cloudwatch_provider.monotonic",
        lambda: provider._last_flush + 31,
    )
    provider.publish_system(SystemMetric(name="fallback_responses", value=0.0, unit="None"))

    assert client.calls, "the elapsed interval should have forced a flush"


def test_fallback_rate_alarm_is_defined_and_valid():
    definitions = {definition.name: definition for definition in build_alarm_definitions()}
    alarm = definitions[ALARM_NAMES["high_fallback_rate"]]

    alarm.validate()
    returned = [query for query in alarm.metric_queries if query.get("ReturnData")]
    assert len(returned) == 1
    assert "fallbacks/delivered" in returned[0]["Expression"]

    sourced = {
        query["MetricStat"]["Metric"]["MetricName"]
        for query in alarm.metric_queries
        if "MetricStat" in query
    }
    assert sourced == {FALLBACK_RESPONSES_METRIC, DELIVERED_RESPONSES_METRIC}
    # Summed, not averaged: a busy period must weigh more than a quiet one.
    assert all(
        query["MetricStat"]["Stat"] == "Sum" for query in alarm.metric_queries if "MetricStat" in query
    )


def test_numeric_repair_is_counted(monkeypatch):
    """Repair silently edits an answer, so it has to be countable."""
    publisher = _capture(monkeypatch)

    response_metrics.record_numeric_repair(2)

    recorded = _by_name(publisher)
    assert recorded["numeric_claim_repairs"].value == 2.0


def test_numeric_repair_count_is_never_negative(monkeypatch):
    publisher = _capture(monkeypatch)

    response_metrics.record_numeric_repair(-1)

    assert _by_name(publisher)["numeric_claim_repairs"].value == 0.0
