"""Base audit sink interface."""

from typing import Protocol

from app.audit.models import AuditEvent


class AuditSink(Protocol):
    """Destination for audit events."""

    name: str

    async def write(self, event: AuditEvent) -> None:
        """Write one audit event to this sink."""
