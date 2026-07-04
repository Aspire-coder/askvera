"""Correlation ID middleware for request tracing."""

from collections.abc import Awaitable, Callable
from re import fullmatch
from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.utils.context import correlation_id_ctx
from utils.logging import get_logger

LOGGER = get_logger("app.middleware.correlation")
CORRELATION_ID_HEADER = "X-Correlation-ID"
MAX_CORRELATION_ID_LENGTH = 128
CORRELATION_ID_PATTERN = r"[A-Za-z0-9._:\-]+"


def _is_valid_correlation_id(value: str | None) -> bool:
    """Return True when an incoming correlation ID is safe to reflect."""
    if not value:
        return False
    if len(value) > MAX_CORRELATION_ID_LENGTH:
        return False
    return fullmatch(CORRELATION_ID_PATTERN, value) is not None


def _resolve_correlation_id(request: Request) -> str:
    """Use a safe client-provided correlation ID or generate a new one."""
    incoming_id = request.headers.get(CORRELATION_ID_HEADER)
    if _is_valid_correlation_id(incoming_id):
        return incoming_id or ""
    return str(uuid4())


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach one correlation ID to every request and response."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Set request context, add response header, and log completion."""
        correlation_id = _resolve_correlation_id(request)
        request.state.correlation_id = correlation_id
        token = correlation_id_ctx.set(correlation_id)
        started = perf_counter()

        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = round((perf_counter() - started) * 1000, 2)
            correlation_id_ctx.reset(token)
            if "response" in locals():
                response.headers[CORRELATION_ID_HEADER] = correlation_id
                LOGGER.info(
                    "request_complete",
                    correlation_id=correlation_id,
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )
