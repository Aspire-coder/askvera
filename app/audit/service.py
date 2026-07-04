"""Backward-compatible audit service wrapper."""

from .dispatcher import AuditDispatcher
from .models import AuditEvent


class AuditService:
    """Compatibility wrapper around the audit dispatcher."""

    def __init__(self, dispatcher: AuditDispatcher | None = None) -> None:
        self._dispatcher = dispatcher or AuditDispatcher()

    async def publish(self, event: AuditEvent) -> None:
        """Publish one audit event through configured sinks."""
        await self._dispatcher.dispatch(event)
