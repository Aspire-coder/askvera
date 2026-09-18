"""Deterministic/local tests for app.metrics.responses.record_dependency_unavailable.

No orchestrator, no network, no AWS: the CloudWatch/collector sinks are
monkeypatched so nothing here ever touches a real metrics provider. These
pin the metric's shape (name, unit, bounded dimensions -- component and
availability) and the fact that `record_delivered_response` alone never
emits it -- callers must call `record_dependency_unavailable` explicitly,
exactly where C5 requires.

`availability` is bounded to "unavailable"/"degraded" (Codex's R02
RetrievalAvailability labels, passed through once that routing exists) or
"exception" (this project's own label for a dependency failure that escaped
as a raised exception, e.g. the retrieve()/generate() except clauses in
chat_orchestrator.py).
"""

from __future__ import annotations

from app.metrics import responses as response_metrics
from app.metrics.models import SystemMetric
from app.metrics.names import DEPENDENCY_UNAVAILABLE_METRIC, SYSTEM_METRIC_DIMENSIONS, SYSTEM_METRIC_NAMES


class _RecordingPublisher:
    def __init__(self) -> None:
        self.metrics: list[SystemMetric] = []

    def publish_system(self, metric: SystemMetric) -> None:
        self.metrics.append(metric)


def _capture(monkeypatch) -> _RecordingPublisher:
    publisher = _RecordingPublisher()
    monkeypatch.setattr(response_metrics, "metrics_publisher", publisher)
    return publisher


def test_dependency_unavailable_metric_is_registered_with_cloudwatch_name():
    assert SYSTEM_METRIC_NAMES["dependency_unavailable"] == DEPENDENCY_UNAVAILABLE_METRIC
    assert DEPENDENCY_UNAVAILABLE_METRIC == "DependencyUnavailable"


def test_dependency_unavailable_has_component_and_availability_dimensions():
    mappings = dict(SYSTEM_METRIC_DIMENSIONS["dependency_unavailable"])
    assert mappings == {"component": "Component", "availability": "Availability"}


def test_records_one_count_with_component_and_availability(monkeypatch):
    publisher = _capture(monkeypatch)

    response_metrics.record_dependency_unavailable("retrieval", "exception")

    assert len(publisher.metrics) == 1
    metric = publisher.metrics[0]
    assert metric.name == "dependency_unavailable"
    assert metric.value == 1.0
    assert metric.unit == "Count"
    assert metric.metadata == {"component": "retrieval", "availability": "exception"}


def test_embedding_component_is_recorded_as_given(monkeypatch):
    publisher = _capture(monkeypatch)

    response_metrics.record_dependency_unavailable("embedding", "exception")

    assert publisher.metrics[0].metadata["component"] == "embedding"


def test_generation_component_is_recorded_as_given(monkeypatch):
    publisher = _capture(monkeypatch)

    response_metrics.record_dependency_unavailable("generation", "exception")

    assert publisher.metrics[0].metadata["component"] == "generation"


def test_r02_availability_values_pass_through(monkeypatch):
    """Once Codex's R02 routing calls this metric with a real
    RetrievalAvailability-derived label, both values must pass through
    unmodified."""
    publisher = _capture(monkeypatch)

    response_metrics.record_dependency_unavailable("retrieval", "unavailable")
    response_metrics.record_dependency_unavailable("retrieval", "degraded")

    availabilities = [metric.metadata["availability"] for metric in publisher.metrics]
    assert availabilities == ["unavailable", "degraded"]


def test_unrecognized_component_is_bounded_to_unknown(monkeypatch):
    """Cardinality guard: an unexpected component string must never pass through
    verbatim into a CloudWatch dimension."""
    publisher = _capture(monkeypatch)

    response_metrics.record_dependency_unavailable("some_new_thing_nobody_approved", "exception")

    assert publisher.metrics[0].metadata["component"] == "unknown"


def test_unrecognized_availability_is_bounded_to_unknown(monkeypatch):
    publisher = _capture(monkeypatch)

    response_metrics.record_dependency_unavailable("retrieval", "some_new_value_nobody_approved")

    assert publisher.metrics[0].metadata["availability"] == "unknown"


def test_delivered_response_alone_never_emits_dependency_unavailable(monkeypatch):
    """The generic delivered/fallback counter must not also fire this metric --
    only an explicit record_dependency_unavailable call may."""
    publisher = _capture(monkeypatch)

    response_metrics.record_delivered_response(
        {"fallback": True, "failure_layer": "dependency_unavailable"}
    )

    names = {metric.name for metric in publisher.metrics}
    assert "dependency_unavailable" not in names
    assert "fallback_by_layer" in names


def test_delivered_response_for_missing_evidence_never_emits_it(monkeypatch):
    publisher = _capture(monkeypatch)

    response_metrics.record_delivered_response({"fallback": True, "failure_layer": "evidence_gate"})

    names = {metric.name for metric in publisher.metrics}
    assert "dependency_unavailable" not in names
