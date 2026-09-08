"""Typed metrics models."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
import os
from socket import gethostname
from typing import Any


def environment_label() -> str:
    """Return the environment dimension every metric and alarm must agree on.

    Published metrics and the alarms that watch them have to name the same
    environment or the alarm sees no data. They previously derived it
    separately, with different fallbacks -- "local" here and "production" in
    app/monitoring/alarms.py -- so they agreed only because APP_ENV happens to
    be set on the box. Both now call this, so agreement is structural.
    """
    return os.environ.get("APP_ENV", os.environ.get("ENVIRONMENT", "local"))


def _environment() -> str:
    """Return current deployment environment label."""
    return environment_label()


def version_label() -> str:
    """Return the version dimension every metric and alarm must agree on."""
    return _version()


def _version() -> str:
    """Return current application version label.

    Falls back to the code-owned settings value rather than "unknown".

    The alarms in app/monitoring/alarms.py filter on settings.APP_VERSION,
    which is the literal "1.0.0". Nothing sets an APP_VERSION environment
    variable on the box, so every metric published a Version of "unknown" and
    every application alarm watched a dimension combination that had no data.
    Confirmed on 2026-09-08 from the service journal, hours after the metrics
    themselves were verified as arriving in CloudWatch.

    Imported inside the function so this module keeps its import-time
    independence from config, which the rest of the metrics package relies on.
    """
    from config import settings

    return os.environ.get("APP_VERSION") or settings.APP_VERSION


@dataclass(frozen=True)
class RequestMetric:
    """One completed HTTP request metric sample."""

    method: str
    path: str
    status_code: int
    duration_ms: float
    success: bool
    correlation_id: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    environment: str = field(default_factory=_environment)
    version: str = field(default_factory=_version)
    hostname: str = field(default_factory=gethostname)
    dimensions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RequestMetricSnapshot:
    """Aggregated in-process request metric counters."""

    request_count: int
    success_count: int
    failure_count: int
    total_duration_ms: float
    average_duration_ms: float


@dataclass(frozen=True)
class SystemMetric:
    """One application health or operational metric sample."""

    name: str
    value: float
    unit: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    environment: str = field(default_factory=_environment)
    version: str = field(default_factory=_version)
    hostname: str = field(default_factory=gethostname)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PipelineMetric:
    """One pipeline stage timing sample."""

    stage: str
    duration_ms: float
    success: bool
    correlation_id: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    environment: str = field(default_factory=_environment)
    version: str = field(default_factory=_version)
    hostname: str = field(default_factory=gethostname)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PipelineStageSnapshot:
    """Aggregated in-process timing counters for one pipeline stage."""

    stage: str
    count: int
    total_duration_ms: float
    average_duration_ms: float
    min_duration_ms: float
    max_duration_ms: float


@dataclass(frozen=True)
class MetricsSnapshot:
    """Full in-process metrics snapshot."""

    request: RequestMetricSnapshot
    pipeline: dict[str, PipelineStageSnapshot]
    system: dict[str, SystemMetric]


@dataclass(frozen=True)
class HealthSummary:
    """Compact application health metric summary."""

    status: str
    cache_hit_ratio: float
    retrieval_failure_rate: float
    governance_blocks: int
    validation_failures: int
    audit_queue_depth: int
