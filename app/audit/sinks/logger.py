"""Structured logging audit sink."""

from app.audit.models import AuditEvent
from utils.logging import get_logger

LOGGER = get_logger("app.audit.sinks.logger")


class LoggerAuditSink:
    """Write audit events to structured JSON logs."""

    name = "logger"

    async def write(self, event: AuditEvent) -> None:
        """Publish one audit event to CloudWatch-friendly logs."""
        LOGGER.info(
            "audit_event",
            correlation_id=event.correlation_id,
            audit=event.model_dump(mode="json"),
        )
