"""Non-blocking audit event publisher."""

import asyncio

from .models import AuditEvent
from .queue import audit_queue, queue_capacity, queue_size, queue_utilization
from utils.logging import get_logger

LOGGER = get_logger("app.audit.publisher")


class AuditPublisher:
    """Single entry point for putting audit events on the queue."""

    async def publish(self, event: AuditEvent) -> None:
        """Enqueue an audit event without blocking the request path."""
        try:
            audit_queue.put_nowait(event)
        except asyncio.QueueFull:
            LOGGER.warning(
                "audit_queue_full_dropped_event",
                correlation_id=event.correlation_id,
                event_type=event.event_type.value,
                queue_size=queue_size(),
                queue_capacity=queue_capacity(),
                queue_utilization=queue_utilization(),
            )


audit_publisher = AuditPublisher()
