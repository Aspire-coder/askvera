"""Tests for the privacy-conscious live pipeline trace window."""

from app.operations.trace_store import PipelineTraceStore


def test_trace_store_orders_stages_and_masks_common_pii() -> None:
    store = PipelineTraceStore(capacity=10)
    store.start(
        "trace-1",
        country="BE",
        language="nl",
        session_id="session-1",
        question_preview="Email me at user@example.com or +32 470 12 34 56",
    )
    store.record("trace-1", "retrieval", success=True, duration_ms=91.237)
    store.record("trace-1", "governance", success=True, duration_ms=14)
    store.finish("trace-1", success=True, metadata={"source_count": 2})

    trace = store.get("trace-1")

    assert trace is not None
    assert trace["question_preview"] == "Email me at [EMAIL] or [PHONE]"
    assert [stage["stage"] for stage in trace["stages"]] == [
        "request_received",
        "governance",
        "retrieval",
        "response_delivered",
    ]
    assert trace["stages"][2]["duration_ms"] == 91.24
    assert trace["completed_at"]


def test_trace_store_is_bounded_and_returns_newest_first() -> None:
    store = PipelineTraceStore(capacity=10)
    for index in range(12):
        store.start(f"trace-{index}")

    latest = store.latest(20)

    assert len(latest) == 10
    assert latest[0]["correlation_id"] == "trace-11"
    assert latest[-1]["correlation_id"] == "trace-2"
