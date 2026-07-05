"""Centralized CloudWatch alarm definitions for ASK Vera."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from socket import gethostname
from typing import Any

from config import settings
from utils.logging import get_logger

from app.metrics.names import (
    AUDIT_QUEUE_DEPTH,
    AVERAGE_REQUEST_DURATION,
    CACHE_HIT_RATIO,
    FAILED_REQUESTS,
    GOVERNANCE_HEALTH,
    MODEL_LATENCY,
    PROMPT_BUILD_LATENCY,
    RETRIEVAL_HEALTH,
    TOTAL_REQUESTS,
    VALIDATION_HEALTH,
)

LOGGER = get_logger("app.monitoring.alarms")

APP_NAMESPACE = settings.CLOUDWATCH_NAMESPACE
EC2_NAMESPACE = "AWS/EC2"
CW_AGENT_NAMESPACE = "CWAgent"
FIREHOSE_NAMESPACE = "AWS/Firehose"

REQUEST_LATENCY_THRESHOLD = settings.REQUEST_LATENCY_THRESHOLD
ERROR_RATE_THRESHOLD = settings.ERROR_RATE_THRESHOLD
CACHE_HIT_THRESHOLD = settings.CACHE_HIT_THRESHOLD
CPU_THRESHOLD = settings.CPU_THRESHOLD
MEMORY_THRESHOLD = settings.MEMORY_THRESHOLD
DISK_THRESHOLD = settings.DISK_THRESHOLD
MODEL_LATENCY_THRESHOLD = settings.MODEL_LATENCY_THRESHOLD
PROMPT_BUILD_LATENCY_THRESHOLD = settings.PROMPT_BUILD_LATENCY_THRESHOLD
PIPELINE_HEALTH_THRESHOLD = settings.PIPELINE_HEALTH_THRESHOLD
AUDIT_QUEUE_DEPTH_THRESHOLD = settings.AUDIT_QUEUE_DEPTH_THRESHOLD
FIREHOSE_DELIVERY_FAILURE_THRESHOLD = settings.FIREHOSE_DELIVERY_FAILURE_THRESHOLD

_ALARM_SUFFIXES = {
    "high_latency": "HighLatency",
    "high_error_rate": "HighErrorRate",
    "no_requests": "NoRequests",
    "governance_health": "GovernanceHealth",
    "retrieval_health": "RetrievalHealth",
    "validation_health": "ValidationHealth",
    "high_model_latency": "HighModelLatency",
    "high_prompt_build_latency": "HighPromptBuildLatency",
    "low_cache_hit": "LowCacheHit",
    "audit_queue_depth": "AuditQueueDepth",
    "firehose_delivery_failures": "FirehoseDeliveryFailures",
    "high_cpu": "HighCPU",
    "high_memory": "HighMemory",
    "high_disk": "HighDisk",
}
ALARM_NAMES = {
    key: f"{settings.CLOUDWATCH_ALARM_PREFIX}-{suffix}"
    for key, suffix in _ALARM_SUFFIXES.items()
}


@dataclass(frozen=True)
class AlarmDefinition:
    """One CloudWatch alarm definition."""

    name: str
    description: str
    metric_name: str | None = None
    namespace: str = APP_NAMESPACE
    statistic: str = "Average"
    period: int = 300
    evaluation_periods: int = 1
    datapoints_to_alarm: int | None = None
    comparison_operator: str = "GreaterThanThreshold"
    threshold: float = 1.0
    unit: str | None = None
    dimensions: dict[str, str] = field(default_factory=dict)
    treat_missing_data: str = "notBreaching"
    metric_queries: list[dict[str, Any]] = field(default_factory=list)

    def validate(self) -> None:
        """Validate fields required by CloudWatch alarm creation."""
        if not self.name:
            raise ValueError("Alarm name is required.")
        if not self.description:
            raise ValueError(f"Alarm description is required for {self.name}.")
        if not self.metric_name and not self.metric_queries:
            raise ValueError(f"Alarm {self.name} requires metric_name or metric_queries.")
        if self.metric_name and self.metric_queries:
            raise ValueError(f"Alarm {self.name} cannot use both metric_name and metric_queries.")
        if self.period <= 0:
            raise ValueError(f"Alarm {self.name} period must be positive.")
        if self.evaluation_periods <= 0:
            raise ValueError(f"Alarm {self.name} evaluation periods must be positive.")
        for key, value in self.dimensions.items():
            if not key or value == "":
                raise ValueError(f"Alarm {self.name} has an invalid dimension {key!r}.")


@dataclass(frozen=True)
class AlarmSetupResult:
    """Result from creating or updating one alarm."""

    name: str
    success: bool
    error: str = ""


class CloudWatchAlarmManager:
    """Create or update CloudWatch alarms from centralized definitions."""

    def __init__(self, client: Any | None = None, enabled: bool | None = None) -> None:
        self.enabled = settings.ENABLE_CLOUDWATCH_ALARMS if enabled is None else enabled
        self.client = client
        if self.enabled and self.client is None:
            self.client = self._build_client()

    def put_alarm(self, definition: AlarmDefinition) -> AlarmSetupResult:
        """Create or update one CloudWatch alarm idempotently."""
        try:
            definition.validate()
            if not self.enabled or not self.client:
                return AlarmSetupResult(name=definition.name, success=True)
            self.client.put_metric_alarm(**self._payload(definition))
            LOGGER.info("cloudwatch_alarm_configured", alarm_name=definition.name)
            return AlarmSetupResult(name=definition.name, success=True)
        except Exception as exc:  # noqa: BLE001 - setup should report failures without crashing callers.
            LOGGER.warning("cloudwatch_alarm_setup_failed", alarm_name=definition.name, error=str(exc))
            return AlarmSetupResult(name=definition.name, success=False, error=str(exc))

    def put_alarms(self, definitions: list[AlarmDefinition]) -> list[AlarmSetupResult]:
        """Create or update multiple CloudWatch alarms."""
        return [self.put_alarm(definition) for definition in definitions]

    def _payload(self, definition: AlarmDefinition) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "AlarmName": definition.name,
            "AlarmDescription": definition.description,
            "ComparisonOperator": definition.comparison_operator,
            "Threshold": definition.threshold,
            "EvaluationPeriods": definition.evaluation_periods,
            "TreatMissingData": definition.treat_missing_data,
        }
        if definition.datapoints_to_alarm is not None:
            payload["DatapointsToAlarm"] = definition.datapoints_to_alarm
        if definition.metric_queries:
            payload["Metrics"] = definition.metric_queries
        else:
            payload.update(
                {
                    "MetricName": definition.metric_name,
                    "Namespace": definition.namespace,
                    "Statistic": definition.statistic,
                    "Period": definition.period,
                    "Dimensions": [
                        {"Name": key, "Value": value}
                        for key, value in sorted(definition.dimensions.items())
                    ],
                }
            )
            if definition.unit:
                payload["Unit"] = definition.unit
        return payload

    @staticmethod
    def _build_client() -> Any | None:
        try:
            import boto3

            return boto3.client("cloudwatch", region_name=settings.AWS_REGION)
        except Exception as exc:  # noqa: BLE001 - alarm setup can be disabled if SDK/client is unavailable.
            LOGGER.warning("cloudwatch_alarm_client_init_failed", error=str(exc))
            return None


def build_alarm_definitions() -> list[AlarmDefinition]:
    """Build all production alarm definitions from settings."""
    hostname = settings.CLOUDWATCH_ALARM_HOSTNAME or gethostname()
    app_dimensions = _app_dimensions(hostname)
    aggregate_dimensions = _aggregate_dimensions()
    definitions = [
        _high_error_rate_alarm(app_dimensions),
        AlarmDefinition(
            name=ALARM_NAMES["high_latency"],
            description="ASK Vera average request latency is above 3 seconds.",
            metric_name=AVERAGE_REQUEST_DURATION,
            namespace=APP_NAMESPACE,
            statistic="Average",
            threshold=REQUEST_LATENCY_THRESHOLD,
            comparison_operator="GreaterThanThreshold",
            dimensions=app_dimensions,
            period=300,
            evaluation_periods=1,
            unit="Milliseconds",
        ),
        AlarmDefinition(
            name=ALARM_NAMES["no_requests"],
            description="ASK Vera received no requests for 15 minutes.",
            metric_name=TOTAL_REQUESTS,
            namespace=APP_NAMESPACE,
            statistic="Sum",
            threshold=1,
            comparison_operator="LessThanThreshold",
            dimensions=app_dimensions,
            period=900,
            evaluation_periods=1,
            treat_missing_data="breaching",
            unit="Count",
        ),
        _health_alarm(ALARM_NAMES["governance_health"], GOVERNANCE_HEALTH, "Governance health dropped below 95%.", aggregate_dimensions),
        _health_alarm(ALARM_NAMES["retrieval_health"], RETRIEVAL_HEALTH, "Retrieval health dropped below 95%.", aggregate_dimensions),
        _health_alarm(ALARM_NAMES["validation_health"], VALIDATION_HEALTH, "Validation health dropped below 95%.", aggregate_dimensions),
        AlarmDefinition(
            name=ALARM_NAMES["high_model_latency"],
            description="ASK Vera model latency is above 5 seconds.",
            metric_name=MODEL_LATENCY,
            namespace=APP_NAMESPACE,
            statistic="Average",
            threshold=MODEL_LATENCY_THRESHOLD,
            comparison_operator="GreaterThanThreshold",
            dimensions=aggregate_dimensions,
            period=300,
            evaluation_periods=1,
            unit="Milliseconds",
        ),
        AlarmDefinition(
            name=ALARM_NAMES["high_prompt_build_latency"],
            description="ASK Vera prompt build latency is above 500 ms.",
            metric_name=PROMPT_BUILD_LATENCY,
            namespace=APP_NAMESPACE,
            statistic="Average",
            threshold=PROMPT_BUILD_LATENCY_THRESHOLD,
            comparison_operator="GreaterThanThreshold",
            dimensions=aggregate_dimensions,
            period=300,
            evaluation_periods=1,
            unit="Milliseconds",
        ),
        AlarmDefinition(
            name=ALARM_NAMES["low_cache_hit"],
            description="ASK Vera cache hit ratio is below 60%.",
            metric_name=CACHE_HIT_RATIO,
            namespace=APP_NAMESPACE,
            statistic="Average",
            threshold=CACHE_HIT_THRESHOLD,
            comparison_operator="LessThanThreshold",
            dimensions=aggregate_dimensions,
            period=300,
            evaluation_periods=1,
            unit="None",
        ),
        AlarmDefinition(
            name=ALARM_NAMES["audit_queue_depth"],
            description="ASK Vera audit queue depth is above 100 events.",
            metric_name=AUDIT_QUEUE_DEPTH,
            namespace=APP_NAMESPACE,
            statistic="Maximum",
            threshold=AUDIT_QUEUE_DEPTH_THRESHOLD,
            comparison_operator="GreaterThanThreshold",
            dimensions=aggregate_dimensions,
            period=300,
            evaluation_periods=1,
            unit="Count",
        ),
        AlarmDefinition(
            name=ALARM_NAMES["firehose_delivery_failures"],
            description="ASK Vera audit Firehose reported delivery failures.",
            metric_name="DeliveryToS3.Failures",
            namespace=FIREHOSE_NAMESPACE,
            statistic="Sum",
            threshold=FIREHOSE_DELIVERY_FAILURE_THRESHOLD,
            comparison_operator="GreaterThanThreshold",
            dimensions={"DeliveryStreamName": settings.AUDIT_FIREHOSE_STREAM},
            period=300,
            evaluation_periods=1,
            unit="Count",
        ),
    ]
    if settings.EC2_INSTANCE_ID:
        definitions.extend(_ec2_alarm_definitions(settings.EC2_INSTANCE_ID))
    return definitions


def _high_error_rate_alarm(dimensions: dict[str, str]) -> AlarmDefinition:
    return AlarmDefinition(
        name=ALARM_NAMES["high_error_rate"],
        description="ASK Vera request error rate is above 5%.",
        threshold=ERROR_RATE_THRESHOLD,
        comparison_operator="GreaterThanThreshold",
        period=300,
        evaluation_periods=1,
        metric_queries=[
            _metric_query("failed", FAILED_REQUESTS, "Sum", dimensions),
            _metric_query("total", TOTAL_REQUESTS, "Sum", dimensions),
            {
                "Id": "error_rate",
                "Expression": "IF(total>0,100*(failed/total),0)",
                "Label": "ErrorRate",
                "ReturnData": True,
            },
        ],
    )


def _health_alarm(name: str, metric_name: str, description: str, dimensions: dict[str, str]) -> AlarmDefinition:
    return AlarmDefinition(
        name=name,
        description=description,
        metric_name=metric_name,
        namespace=APP_NAMESPACE,
        statistic="Average",
        threshold=PIPELINE_HEALTH_THRESHOLD,
        comparison_operator="LessThanThreshold",
        dimensions=dimensions,
        period=300,
        evaluation_periods=1,
        unit="None",
    )


def _ec2_alarm_definitions(instance_id: str) -> list[AlarmDefinition]:
    return [
        AlarmDefinition(
            name=ALARM_NAMES["high_cpu"],
            description="ASK Vera EC2 CPU utilization is above 80%.",
            metric_name="CPUUtilization",
            namespace=EC2_NAMESPACE,
            statistic="Average",
            threshold=CPU_THRESHOLD,
            comparison_operator="GreaterThanThreshold",
            dimensions={"InstanceId": instance_id},
            period=300,
            evaluation_periods=2,
            unit="Percent",
        ),
        AlarmDefinition(
            name=ALARM_NAMES["high_memory"],
            description="ASK Vera EC2 memory utilization is above 80%. Requires CloudWatch Agent.",
            metric_name="mem_used_percent",
            namespace=CW_AGENT_NAMESPACE,
            statistic="Average",
            threshold=MEMORY_THRESHOLD,
            comparison_operator="GreaterThanThreshold",
            dimensions={"InstanceId": instance_id},
            period=300,
            evaluation_periods=2,
            unit="Percent",
        ),
        AlarmDefinition(
            name=ALARM_NAMES["high_disk"],
            description="ASK Vera EC2 disk utilization is above 85%. Requires CloudWatch Agent.",
            metric_name="disk_used_percent",
            namespace=CW_AGENT_NAMESPACE,
            statistic="Average",
            threshold=DISK_THRESHOLD,
            comparison_operator="GreaterThanThreshold",
            dimensions={"InstanceId": instance_id},
            period=300,
            evaluation_periods=2,
            unit="Percent",
        ),
    ]


def _metric_query(query_id: str, metric_name: str, statistic: str, dimensions: dict[str, str]) -> dict[str, Any]:
    return {
        "Id": query_id,
        "MetricStat": {
            "Metric": {
                "Namespace": APP_NAMESPACE,
                "MetricName": metric_name,
                "Dimensions": [
                    {"Name": key, "Value": value}
                    for key, value in sorted(dimensions.items())
                ],
            },
            "Period": 300,
            "Stat": statistic,
        },
        "ReturnData": False,
    }


def _app_dimensions(hostname: str) -> dict[str, str]:
    return {
        "Environment": _environment(),
        "Version": settings.APP_VERSION,
        "Hostname": hostname,
    }


def _aggregate_dimensions() -> dict[str, str]:
    return {
        "Environment": _environment(),
        "Version": settings.APP_VERSION,
    }


def _environment() -> str:
    return os.environ.get("APP_ENV", os.environ.get("ENVIRONMENT", "production"))
