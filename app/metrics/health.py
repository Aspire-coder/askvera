"""Pipeline health metrics, recorded and actually published.

MetricsCollector has carried recorders for governance, validation, retrieval and
cache health since the monitoring work landed, and CloudWatch has carried alarms
watching the metrics they produce. Nothing in the application ever called them.

The alarms were therefore permanently silent: GovernanceHealth,
ValidationHealth, RetrievalHealth, CacheHitRatio and AuditQueueDepth all use
treat_missing_data="notBreaching", so with no data they sit in OK forever and
look like health rather than absence. Verified on 2026-09-07 by searching the
whole application for callers and finding only tests.

Recording and publishing are deliberately separate in this package: the
collector serves the in-process /health summary, the publisher forwards to
CloudWatch. Both are needed, so these helpers do both, and no failure here is
allowed to reach a user request.
"""

from __future__ import annotations

from utils.logging import get_logger

from .collector import metrics_collector
from .models import SystemMetric
from .publisher import metrics_publisher

LOGGER = get_logger("app.metrics.health")


def record_governance_outcome(*, allowed: bool, provider_failed: bool = False) -> None:
    """Record one governance decision.

    A refusal is not ill health. Governance blocking an income claim is the
    system working, so a block updates its counter but leaves the health gauge
    alone; only a provider failure -- governance unable to reach a verdict --
    counts against health.
    """
    if provider_failed:
        _safely(metrics_collector.record_governance_provider_failure, "governance_health")
    elif allowed:
        _safely(metrics_collector.record_governance_allow, "governance_health")
    else:
        _safely(metrics_collector.record_governance_block, None)


def record_validation_outcome(*, has_critical: bool) -> None:
    """Record whether output validation passed or failed critically."""
    if has_critical:
        _safely(metrics_collector.record_validation_critical, "validation_health")
    else:
        _safely(metrics_collector.record_validation_passed, "validation_health")


def record_cache_outcome(*, hit: bool) -> None:
    """Record one cache read, updating the hit ratio."""
    recorder = metrics_collector.record_cache_hit if hit else metrics_collector.record_cache_miss
    _safely(recorder, "cache_hit_ratio")


def record_retrieval_outcome(*, success: bool) -> None:
    """Record whether retrieval completed.

    The collector only ever had record_retrieval_failure, which drives
    retrieval_health to 0.0 with nothing to drive it back up. Governance and
    validation both have a success recorder; retrieval did not. Wired as-is,
    RetrievalHealth would have latched at 0.0 on the first failure and left the
    alarm permanently firing -- as useless as the silence it replaced. The
    success path is added here.

    Returning zero documents is a legitimate no-match, not a failure. Only an
    exception from the provider counts.
    """
    if success:
        _safely(
            lambda: metrics_collector.record_system(
                SystemMetric(name="retrieval_health", value=1.0, unit="None")
            ),
            "retrieval_health",
        )
    else:
        _safely(metrics_collector.record_retrieval_failure, "retrieval_health")


def record_audit_queue_depth(depth: int) -> None:
    """Record the current audit queue depth.

    Sampled on enqueue rather than on a timer: depth only changes when events
    are added or drained, and a timer would need a lifecycle this package does
    not otherwise have.
    """
    _safely(lambda: metrics_collector.record_audit_queue_depth(depth), "audit_queue_depth")


def _safely(recorder, publish_metric_name: str | None) -> None:
    """Record, then publish the resulting sample, swallowing any failure.

    Health bookkeeping must never turn a working request into a failed one.
    """
    try:
        recorder()
        if publish_metric_name is None:
            return
        metric = metrics_collector.system_snapshot(publish_metric_name)
        if metric is not None:
            metrics_publisher.publish_system(metric)
    except Exception as exc:  # noqa: BLE001 - metrics must never break a request.
        LOGGER.warning("health_metric_failed", metric=publish_metric_name, error=str(exc))
