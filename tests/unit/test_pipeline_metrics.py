"""Unit tests for pipeline stage metrics."""

from app.metrics import (
    STAGE_GOVERNANCE,
    STAGE_MODEL_GENERATE,
    STAGE_PROMPT_BUILD,
    STAGE_RESPONSE_BUILD,
    STAGE_RETRIEVAL,
    STAGE_VALIDATION,
    MetricsCollector,
    PipelineMetric,
)
from app.metrics.pipeline import record_pipeline_metric


class FakePublisher:
    def __init__(self) -> None:
        self.published = []

    def publish_pipeline(self, metric, snapshot) -> None:
        self.published.append((metric, snapshot))


def _metric(stage: str, duration_ms: float, success: bool = True) -> PipelineMetric:
    return PipelineMetric(
        stage=stage,
        duration_ms=duration_ms,
        success=success,
        correlation_id="cid",
    )


def test_pipeline_metrics_track_average_min_and_max_duration() -> None:
    collector = MetricsCollector()

    collector.record_pipeline(_metric(STAGE_RETRIEVAL, 100.0))
    snapshot = collector.record_pipeline(_metric(STAGE_RETRIEVAL, 300.0))

    assert snapshot.stage == STAGE_RETRIEVAL
    assert snapshot.count == 2
    assert snapshot.total_duration_ms == 400.0
    assert snapshot.average_duration_ms == 200.0
    assert snapshot.min_duration_ms == 100.0
    assert snapshot.max_duration_ms == 300.0


def test_pipeline_metrics_record_failed_stage() -> None:
    collector = MetricsCollector()

    snapshot = collector.record_pipeline(_metric(STAGE_MODEL_GENERATE, 50.0, success=False))

    assert snapshot.count == 1
    assert snapshot.average_duration_ms == 50.0
    assert snapshot.min_duration_ms == 50.0
    assert snapshot.max_duration_ms == 50.0


def test_pipeline_metric_helper_publishes_snapshot() -> None:
    collector = MetricsCollector()
    publisher = FakePublisher()

    record_pipeline_metric(
        stage=STAGE_GOVERNANCE,
        duration_ms=12.0,
        success=True,
        correlation_id="cid",
        collector=collector,
        publisher=publisher,
    )

    assert len(publisher.published) == 1
    metric, snapshot = publisher.published[0]
    assert metric.stage == STAGE_GOVERNANCE
    assert snapshot.count == 1


def test_standard_pipeline_stage_names_are_stable() -> None:
    assert STAGE_GOVERNANCE == "governance"
    assert STAGE_RETRIEVAL == "retrieval"
    assert STAGE_PROMPT_BUILD == "prompt_build"
    assert STAGE_MODEL_GENERATE == "model_generate"
    assert STAGE_VALIDATION == "validation"
    assert STAGE_RESPONSE_BUILD == "response_build"
