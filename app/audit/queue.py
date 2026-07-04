"""Bounded in-memory audit event queue."""

import asyncio

from .models import AuditEvent

AUDIT_QUEUE_MAX_SIZE = 10000

audit_queue: asyncio.Queue[AuditEvent] = asyncio.Queue(maxsize=AUDIT_QUEUE_MAX_SIZE)


def queue_size() -> int:
    """Return the current number of queued audit events."""
    return audit_queue.qsize()


def queue_capacity() -> int:
    """Return the configured maximum queue size."""
    return audit_queue.maxsize


def queue_utilization() -> float:
    """Return queue usage as a value between 0 and 1."""
    if audit_queue.maxsize <= 0:
        return 0.0
    return round(audit_queue.qsize() / audit_queue.maxsize, 4)
