"""Typed metrics models."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


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
    dimensions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RequestMetricSnapshot:
    """Aggregated in-process request metric counters."""

    request_count: int
    success_count: int
    failure_count: int
    total_duration_ms: float
    average_duration_ms: float
