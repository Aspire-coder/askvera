"""In-memory audit metrics sink foundation."""

from collections import Counter

from app.audit.models import AuditEvent


class MetricsAuditSink:
    """Track event counts in memory for future CloudWatch metrics."""

    name = "metrics"

    def __init__(self) -> None:
        self._counts: Counter[str] = Counter()

    async def write(self, event: AuditEvent) -> None:
        """Increment the count for this audit event type."""
        self._counts[event.event_type.value] += 1

    def get_count(self, event_type: str) -> int:
        """Return the in-memory count for one event type."""
        return self._counts[event_type]
