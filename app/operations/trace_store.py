"""Bounded in-process trace history for the live pipeline visualizer."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from threading import RLock
from typing import Any

from utils.redaction import redact_common_pii


PIPELINE_ORDER = {
    "request_received": 0,
    "governance": 1,
    "retrieval": 2,
    "prompt_build": 3,
    "model_generate": 4,
    "validation": 5,
    "response_build": 6,
    "response_delivered": 7,
}


@dataclass
class TraceStage:
    """One completed or active stop in a chat request trace."""

    stage: str
    status: str
    duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineTrace:
    """A privacy-conscious view of one chat request moving through the system."""

    correlation_id: str
    country: str = ""
    language: str = ""
    session_id: str = ""
    question_preview: str = ""
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str = ""
    stages: list[TraceStage] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PipelineTraceStore:
    """Keep a small recent trace window without adding latency to chat requests."""

    def __init__(self, capacity: int = 100) -> None:
        self.capacity = max(10, capacity)
        self._lock = RLock()
        self._traces: OrderedDict[str, PipelineTrace] = OrderedDict()

    def start(
        self,
        correlation_id: str,
        *,
        country: str = "",
        language: str = "",
        session_id: str = "",
        question_preview: str = "",
    ) -> PipelineTrace:
        with self._lock:
            trace = PipelineTrace(
                correlation_id=correlation_id,
                country=country,
                language=language,
                session_id=session_id,
                question_preview=redact_common_pii(" ".join(question_preview.split()))[:180],
            )
            self._traces[correlation_id] = trace
            self._traces.move_to_end(correlation_id)
            while len(self._traces) > self.capacity:
                self._traces.popitem(last=False)
            self._record(trace, "request_received", "complete")
            return trace

    def record(
        self,
        correlation_id: str,
        stage: str,
        *,
        success: bool,
        duration_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            trace = self._traces.get(correlation_id)
            if trace is None:
                trace = PipelineTrace(correlation_id=correlation_id)
                self._traces[correlation_id] = trace
            self._record(
                trace,
                stage,
                "complete" if success else "error",
                duration_ms=duration_ms,
                metadata=metadata,
            )
            self._traces.move_to_end(correlation_id)

    def finish(self, correlation_id: str, *, success: bool, metadata: dict[str, Any] | None = None) -> None:
        with self._lock:
            trace = self._traces.get(correlation_id)
            if trace is None:
                trace = PipelineTrace(correlation_id=correlation_id)
                self._traces[correlation_id] = trace
            self._record(trace, "response_delivered", "complete" if success else "error", metadata=metadata)
            trace.completed_at = datetime.now(UTC).isoformat()

    def latest(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            traces = list(reversed(self._traces.values()))[: max(1, min(limit, self.capacity))]
            return [trace.to_dict() for trace in traces]

    def get(self, correlation_id: str) -> dict[str, Any] | None:
        with self._lock:
            trace = self._traces.get(correlation_id)
            return trace.to_dict() if trace else None

    def reset(self) -> None:
        with self._lock:
            self._traces.clear()

    def _record(
        self,
        trace: PipelineTrace,
        stage: str,
        status: str,
        *,
        duration_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        trace.stages = [existing for existing in trace.stages if existing.stage != stage]
        trace.stages.append(
            TraceStage(
                stage=stage,
                status=status,
                duration_ms=round(float(duration_ms or 0.0), 2),
                metadata=dict(metadata or {}),
            )
        )
        trace.stages.sort(key=lambda item: PIPELINE_ORDER.get(item.stage, 99))


pipeline_trace_store = PipelineTraceStore()
