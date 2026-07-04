"""Compatibility wrapper for publishing business audit events."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.audit.enums import AuditEventType
from app.audit.models import AuditEvent
from app.audit.publisher import audit_publisher
from utils.logging import get_logger

LOGGER = get_logger("services.audit")


def _event_type(raw_type: str | None) -> AuditEventType:
    """Map legacy audit type values to the new audit event enum."""
    if raw_type == "chat":
        return AuditEventType.CHAT_RESPONSE
    return AuditEventType.ERROR


async def publish_audit_event(event: dict[str, Any], correlation_id: str) -> None:
    """Publish one business audit event through the async audit pipeline."""
    audit_event = AuditEvent(
        event_id=str(uuid4()),
        correlation_id=correlation_id,
        timestamp=datetime.now(UTC),
        event_type=_event_type(event.get("type")),
        country=event.get("country"),
        language=event.get("language"),
        status="success",
        metadata={key: value for key, value in event.items() if key not in {"country", "language"}},
    )
    await audit_publisher.publish(audit_event)


def write_audit_event(event: dict[str, Any], correlation_id: str) -> None:
    """Queue one audit event without calling Firehose directly.

    This synchronous wrapper preserves existing route call sites while keeping
    one canonical audit delivery path: publisher -> queue -> worker -> sinks.
    """
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(publish_audit_event(event, correlation_id))
        return

    loop.create_task(publish_audit_event(event, correlation_id))
    LOGGER.info("audit_event_queued", correlation_id=correlation_id, event_type=event.get("type", "unknown"))
