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

# Bounded, enumerable component labels for record_dependency_unavailable's
# `component` dimension. Mirrors
# app.orchestrator.dependency_contract.DEPENDENCY_COMPONENTS; duplicated as a
# plain set (rather than imported) so this metrics module keeps no
# import-time dependency on the orchestrator package. Kept in sync by the
# "unknown" test in test_dependency_metrics.py.
DEPENDENCY_COMPONENTS = frozenset({"retrieval", "embedding", "generation"})

# Bounded, enumerable values for record_dependency_unavailable's
# `availability` dimension. "unavailable" and "degraded" are Codex's R02
# RetrievalAvailability labels (RetrievalResult.availability), passed
# through once that routing exists; "exception" is this project's own label
# for a dependency failure that escaped as a raised exception (the
# retrieve()/generate() except clauses in chat_orchestrator.py) rather than
# arriving as a routed availability value.
DEPENDENCY_AVAILABILITY_VALUES = frozenset({"unavailable", "degraded", "exception"})

UNKNOWN_DEPENDENCY_VALUE = "unknown"


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


def record_dependency_unavailable(component: str, availability: str) -> None:
    """Count one response delivered because a dependency was unavailable.

    Emitted at every dependency_unavailable fallback path in
    `AIOrchestrator._handle_scrubbed_chat` -- today, the retrieve() catch
    (component "retrieval" or "embedding", per
    app.orchestrator.dependency_contract.dependency_component_for_exception)
    and the generate() catch (component "generation"); at integration, also
    Codex's R02 routing of `RetrievalResult.availability` (component
    "retrieval") -- and at nothing else.

    It must NOT be emitted for missing evidence, a scope refusal, a
    guardrail block, a ConfigurationError, or a low-confidence answer: none
    of those are dependency outages, and folding them in here would make
    this metric useless for paging on a real one. This is the
    alarm-facing counterpart to
    `fallback_by_layer{failure_layer=dependency_unavailable}`, which already
    counts the same events but cannot be alarmed on directly without also
    picking up every other fallback layer that shares that metric name's
    dimension set. See docs/conversation-quality/phase2/
    DEPENDENCY_ALARM_SPEC.md for how the two relate, and how this differs
    from RetrievalHealth (measured before final evidence approval, so a
    non-empty *degraded* result can still count as provider success there
    even when the delivered answer ends up recording a dependency failure
    here).

    `component` is restricted to `DEPENDENCY_COMPONENTS` so the CloudWatch
    dimension stays bounded; anything unrecognized is recorded as "unknown"
    rather than passed through verbatim. `availability` is restricted the
    same way to `DEPENDENCY_AVAILABILITY_VALUES` ("unavailable"/"degraded"
    from Codex's R02 enum, or "exception" for a dependency failure that
    escaped as a raised exception rather than a routed availability value).
    """
    safe_component = component if component in DEPENDENCY_COMPONENTS else UNKNOWN_DEPENDENCY_VALUE
    safe_availability = (
        availability if availability in DEPENDENCY_AVAILABILITY_VALUES else UNKNOWN_DEPENDENCY_VALUE
    )
    _record(
        SystemMetric(
            name="dependency_unavailable",
            value=1.0,
            unit="Count",
            metadata={
                "component": safe_component,
                "availability": safe_availability,
            },
        )
    )


def record_numeric_repair(removed_claim_count: int) -> None:
    """Count one answer whose numbers were edited by grounding repair.

    Repair is a silent edit to an answer a user is about to read, and it is not
    always right: on 2026-09-07 it removed a correct, document-backed figure
    because a heading two lines above the claim supplied the wrong subject. The
    removal itself is already logged, but nothing counted it, so there was no
    way to notice repair firing more often after a change -- only to stumble on
    one instance in a transcript.

    Counting makes the weekly review possible: if this rises, sample the
    output_validator_numeric_claims_repaired log entries and check whether the
    removed figures were genuinely ungrounded.
    """
    _record(
        SystemMetric(
            name="numeric_claim_repairs",
            value=float(max(0, removed_claim_count)),
            unit="Count",
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
