"""Audit subsystem lifecycle management."""

import asyncio

from .dispatcher import AuditDispatcher
from .queue import audit_queue, queue_size
from .worker import audit_worker
from utils.logging import get_logger

LOGGER = get_logger("app.audit.lifecycle")


class AuditLifecycle:
    """Start and stop audit background workers."""

    def __init__(self, dispatcher: AuditDispatcher) -> None:
        self._dispatcher = dispatcher
        self._worker_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Start the audit worker if it is not already running."""
        if self._worker_task and not self._worker_task.done():
            return
        self._worker_task = asyncio.create_task(audit_worker(self._dispatcher))
        LOGGER.info("audit_lifecycle_started")

    async def stop(self) -> None:
        """Drain queued events and stop the audit worker."""
        LOGGER.info("audit_lifecycle_draining", queue_size=queue_size())
        await audit_queue.join()
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                LOGGER.info("audit_worker_stopped")
        self._worker_task = None
