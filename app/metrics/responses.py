"""Delivered-response outcome metrics.

Every answer the user actually receives is counted here, split by whether it
was a real grounded answer or a fallback, and by which pipeline layer produced
the fallback.

Why this exists: `response_source` and `failure_layer` were already written to
the application log on every response, but nothing counted them. A regression
that pushed answers into fallback was therefore invisible until somebody read a
transcript and noticed. `FallbackResponses` is emitted as 1.0 or 0.0 per
delivered response specifically so that its CloudWatch *Average* over a period
is the fallback rate directly, with no metric math needed at alarm time.
"""

from __future__ import annotations

from typing import Any

from utils.logging import get_logger

from .collector import metrics_collector
from .models import SystemMetric
from .publisher import metrics_publisher

LOGGER = get_logger("app.metrics.responses")

# Fallbacks carry a failure_layer; deliberate non-fallback responses do not.
# Recorded under this label so the by-layer breakdown still sums to the
# fallback total rather than silently dropping unlabelled fallbacks.
UNLABELLED_LAYER = "unlabelled"


def record_delivered_response(metadata: dict[str, Any] | None) -> None:
    """Count one response as delivered, and as a fallback when it is one.

    Takes the response metadata rather than the ChatResponse so that this stays
    usable from anywhere a response is finalised, and so tests need no model.
    """
    metadata = metadata or {}
    is_fallback = bool(metadata.get("fallback"))

    _record(SystemMetric(name="delivered_responses", value=1.0, unit="Count"))
    _record(SystemMetric(name="fallback_responses", value=1.0 if is_fallback else 0.0, unit="None"))

    if is_fallback:
        layer = str(metadata.get("failure_layer") or "").strip() or UNLABELLED_LAYER
        _record(
            SystemMetric(
                name="fallback_by_layer",
                value=1.0,
                unit="Count",
                metadata={"failure_layer": layer},
            )
        )


def _record(metric: SystemMetric) -> None:
    """Record in-process and publish, never letting metrics break a response.

    A delivered answer must not be turned into an error by the bookkeeping that
    describes it, so every failure here is swallowed. The publisher already
    guards its own provider calls; this covers the collector and any future
    provider that raises before reaching that guard.
    """
    try:
        metrics_collector.record_system(metric)
        metrics_publisher.publish_system(metric)
    except Exception as exc:  # noqa: BLE001 - metrics must never break a delivered answer.
        LOGGER.warning("delivered_response_metric_failed", metric=metric.name, error=str(exc))
