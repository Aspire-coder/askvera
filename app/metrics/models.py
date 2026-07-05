"""Typed metrics models."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
import os
from socket import gethostname
from typing import Any


def _environment() -> str:
    """Return current deployment environment label."""
    return os.environ.get("APP_ENV", os.environ.get("ENVIRONMENT", "local"))


def _version() -> str:
    """Return current application version label."""
    return os.environ.get("APP_VERSION", "unknown")


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
