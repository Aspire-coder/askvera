"""Background audit queue worker."""

from .dispatcher import AuditDispatcher
from .queue import audit_queue
from utils.logging import get_logger

LOGGER = get_logger("app.audit.worker")


async def audit_worker(dispatcher: AuditDispatcher) -> None:
    """Continuously publish queued audit events."""
    LOGGER.info("audit_worker_started")
    while True:
        event = await audit_queue.get()
        try:
            await dispatcher.dispatch(event)
        except Exception:
            LOGGER.exception(
                "audit_worker_dispatch_failed",
                correlation_id=event.correlation_id,
                event_type=event.event_type.value,
            )
        finally:
            audit_queue.task_done()
