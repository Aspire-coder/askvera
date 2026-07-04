"""API request middleware."""

from collections.abc import Awaitable, Callable
from collections import defaultdict, deque
from time import monotonic

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings
from utils.logging import get_logger

LOGGER = get_logger("api.middleware")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Small per-process rate limiter for public widget write endpoints."""

    def __init__(self, app: object) -> None:
        super().__init__(app)
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Reject obvious bursts before they reach AWS-backed services."""
        if request.url.path not in settings.RATE_LIMIT_PATHS:
            return await call_next(request)

        forwarded_for = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded_for.split(",", 1)[0].strip() if forwarded_for else ""
        if not client_ip and request.client:
            client_ip = request.client.host
        key = f"{client_ip or 'unknown'}:{request.url.path}"
        now = monotonic()
        window_start = now - settings.RATE_LIMIT_WINDOW_SECONDS
        history = self._requests[key]
        while history and history[0] < window_start:
            history.popleft()
        if len(history) >= settings.RATE_LIMIT_MAX_REQUESTS:
            LOGGER.warning("rate_limit_exceeded", path=request.url.path, client_ip=client_ip or "unknown")
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": {"code": "RATE_LIMITED", "message": "Too many requests. Please try again shortly."},
                    "correlationId": getattr(request.state, "correlation_id", "unknown"),
                },
            )
        history.append(now)
        return await call_next(request)
