"""Dispatch audit events to registered sinks."""

from collections.abc import Sequence

from .models import AuditEvent
from .sinks.base import AuditSink
from .sinks.logger import LoggerAuditSink
from utils.logging import get_logger

LOGGER = get_logger("app.audit.dispatcher")


class AuditDispatcher:
    """Fan out audit events to all configured sinks."""

    def __init__(self, sinks: Sequence[AuditSink] | None = None) -> None:
        self._sinks = list(sinks or [LoggerAuditSink()])

    @property
    def sinks(self) -> tuple[AuditSink, ...]:
        """Return registered sinks."""
        return tuple(self._sinks)

    def add_sink(self, sink: AuditSink) -> None:
        """Register or replace a sink by name."""
        sink_name = getattr(sink, "name", sink.__class__.__name__)
        self._sinks = [existing for existing in self._sinks if getattr(existing, "name", existing.__class__.__name__) != sink_name]
        self._sinks.append(sink)

    async def start_sinks(self) -> None:
        """Start sinks that expose an async start hook."""
        for sink in self._sinks:
            start = getattr(sink, "start", None)
            if callable(start):
                await start()

    async def stop_sinks(self) -> None:
        """Stop sinks that expose an async stop hook."""
        for sink in reversed(self._sinks):
            stop = getattr(sink, "stop", None)
            if callable(stop):
                await stop()

    async def dispatch(self, event: AuditEvent) -> None:
        """Write one event to every sink without letting one sink stop others."""
        for sink in self._sinks:
            try:
                await sink.write(event)
            except Exception:
                LOGGER.exception(
                    "audit_sink_write_failed",
                    correlation_id=event.correlation_id,
                    sink=getattr(sink, "name", sink.__class__.__name__),
                    event_type=event.event_type.value,
                )


audit_dispatcher = AuditDispatcher()
