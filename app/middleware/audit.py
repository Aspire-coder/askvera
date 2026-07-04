"""Audit middleware for request-complete events."""

from collections.abc import Awaitable, Callable
from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.audit.enums import AuditEventType
from app.audit.models import AuditEvent
from app.audit.publisher import AuditPublisher, audit_publisher
from app.utils.request_context import get_correlation_id


class AuditMiddleware(BaseHTTPMiddleware):
    """Create lightweight audit events for completed HTTP requests."""

    def __init__(self, app: object, publisher: AuditPublisher | None = None) -> None:
        super().__init__(app)
        self._publisher = publisher or audit_publisher

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Enqueue a request-complete audit event without waiting for publishing."""
        started = perf_counter()
        response = await call_next(request)
        latency_ms = round((perf_counter() - started) * 1000)
        forwarded_for = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded_for.split(",", 1)[0].strip() if forwarded_for else None
        if not client_ip and request.client:
            client_ip = request.client.host

        event = AuditEvent(
            event_id=str(uuid4()),
            correlation_id=get_correlation_id(request),
            event_type=AuditEventType.HTTP_REQUEST,
            ip_address=client_ip,
            user_agent=request.headers.get("user-agent"),
            status="success" if response.status_code < 400 else "error",
            latency_ms=latency_ms,
            metadata={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
            },
        )
        await self._publisher.publish(event)
        return response
