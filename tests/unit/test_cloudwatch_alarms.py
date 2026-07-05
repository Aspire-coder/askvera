"""Unit tests for CloudWatch alarm definitions."""

from app.monitoring.alarms import (
    ALARM_NAMES,
    AlarmDefinition,
    CloudWatchAlarmManager,
    build_alarm_definitions,
)


class FakeCloudWatchClient:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls = []

    def put_metric_alarm(self, **kwargs) -> None:
        if self.fail:
            raise RuntimeError("cloudwatch unavailable")
        self.calls.append(kwargs)


def test_alarm_names_are_standardized() -> None:
    assert ALARM_NAMES["high_latency"] == "AskVera-HighLatency"
    assert ALARM_NAMES["high_error_rate"] == "AskVera-HighErrorRate"
    assert ALARM_NAMES["governance_health"] == "AskVera-GovernanceHealth"
    assert ALARM_NAMES["retrieval_health"] == "AskVera-RetrievalHealth"
    assert ALARM_NAMES["validation_health"] == "AskVera-ValidationHealth"
    assert ALARM_NAMES["high_model_latency"] == "AskVera-HighModelLatency"
    assert ALARM_NAMES["low_cache_hit"] == "AskVera-LowCacheHit"
    assert ALARM_NAMES["audit_queue_depth"] == "AskVera-AuditQueueDepth"


def test_build_alarm_definitions_contains_core_alarms() -> None:
    definitions = build_alarm_definitions()
    names = {definition.name for definition in definitions}

    assert ALARM_NAMES["high_latency"] in names
    assert ALARM_NAMES["high_error_rate"] in names
    assert ALARM_NAMES["governance_health"] in names
    assert ALARM_NAMES["retrieval_health"] in names
    assert ALARM_NAMES["validation_health"] in names
    assert ALARM_NAMES["high_model_latency"] in names
    assert ALARM_NAMES["high_prompt_build_latency"] in names
    assert ALARM_NAMES["low_cache_hit"] in names
    assert ALARM_NAMES["audit_queue_depth"] in names
    assert ALARM_NAMES["firehose_delivery_failures"] in names


def test_alarm_descriptions_include_operational_context() -> None:
    definition = next(
        alarm for alarm in build_alarm_definitions()
        if alarm.name == ALARM_NAMES["high_latency"]
    )

    assert "Impact:" in definition.description
    assert "First step:" in definition.description
    assert "Runbook:" in definition.description


def test_alarm_definition_validation_requires_metric_or_query() -> None:
    definition = AlarmDefinition(name="AskVera-Test", description="Missing metric")

    try:
        definition.validate()
    except ValueError as exc:
        assert "metric_name or metric_queries" in str(exc)
    else:
        raise AssertionError("Expected invalid alarm definition to fail validation.")


def test_alarm_manager_is_noop_when_disabled() -> None:
    client = FakeCloudWatchClient()
    manager = CloudWatchAlarmManager(client=client, enabled=False)
    definition = AlarmDefinition(
        name="AskVera-Test",
        description="Test alarm",
        metric_name="TotalRequests",
        dimensions={"Environment": "test"},
    )

    result = manager.put_alarm(definition)

    assert result.success is True
    assert client.calls == []


def test_alarm_manager_creates_metric_alarm_payload() -> None:
    client = FakeCloudWatchClient()
    manager = CloudWatchAlarmManager(client=client, enabled=True)
    definition = AlarmDefinition(
        name="AskVera-Test",
        description="Test alarm",
        metric_name="AverageRequestDuration",
        namespace="ASKVera",
        statistic="Average",
        threshold=3000,
        comparison_operator="GreaterThanThreshold",
        dimensions={"Environment": "test", "Version": "1.0.0"},
        unit="Milliseconds",
    )

    result = manager.put_alarm(definition)

    assert result.success is True
    assert len(client.calls) == 1
    payload = client.calls[0]
    assert payload["AlarmName"] == "AskVera-Test"
    assert payload["MetricName"] == "AverageRequestDuration"
    assert payload["Namespace"] == "ASKVera"
    assert payload["Threshold"] == 3000
    assert payload["Unit"] == "Milliseconds"


def test_alarm_manager_creates_metric_math_alarm_payload() -> None:
    client = FakeCloudWatchClient()
    manager = CloudWatchAlarmManager(client=client, enabled=True)
    definition = next(
        alarm for alarm in build_alarm_definitions()
        if alarm.name == ALARM_NAMES["high_error_rate"]
    )

    result = manager.put_alarm(definition)

    assert result.success is True
    payload = client.calls[0]
    assert payload["AlarmName"] == ALARM_NAMES["high_error_rate"]
    assert payload["Metrics"][2]["Id"] == "error_rate"
    assert payload["Metrics"][2]["ReturnData"] is True


def test_alarm_manager_reports_cloudwatch_failures() -> None:
    client = FakeCloudWatchClient(fail=True)
    manager = CloudWatchAlarmManager(client=client, enabled=True)
    definition = AlarmDefinition(
        name="AskVera-Test",
        description="Test alarm",
        metric_name="TotalRequests",
        dimensions={"Environment": "test"},
    )

    result = manager.put_alarm(definition)

    assert result.success is False
    assert "cloudwatch unavailable" in result.error
