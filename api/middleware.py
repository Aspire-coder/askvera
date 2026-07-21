"""API request middleware."""

from collections.abc import Awaitable, Callable
from time import perf_counter

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings
from services.security_state import SecurityStateUnavailable, security_state
from utils.logging import get_logger

LOGGER = get_logger("api.middleware")


def _correlation_id(request: Request) -> str:
    return str(getattr(request.state, "correlation_id", "unknown"))


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    # Nginx appends the actual peer address to X-Forwarded-For. Using the last
    # value prevents a caller-supplied first entry from bypassing rate limits.
    client_ip = forwarded_for.rsplit(",", 1)[-1].strip() if forwarded_for else ""
    if not client_ip and request.client:
        client_ip = request.client.host
    return client_ip or "unknown"


def _error(status_code: int, code: str, message: str, request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {"code": code, "message": message},
            "correlationId": _correlation_id(request),
        },
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Shared endpoint-specific rate limiter with a local development fallback."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Reject obvious bursts before they reach AWS-backed services."""
        limit = settings.RATE_LIMIT_POLICIES.get(request.url.path)
        if limit is None:
            return await call_next(request)

        client_ip = _client_ip(request)
        try:
            allowed = security_state.allow_request(
                client_ip,
                request.url.path,
                limit,
                settings.RATE_LIMIT_WINDOW_SECONDS,
            )
        except SecurityStateUnavailable:
            LOGGER.exception(
                "rate_limit_state_unavailable",
                path=request.url.path,
                correlation_id=_correlation_id(request),
            )
            return _error(503, "SERVICE_UNAVAILABLE", "Service is temporarily unavailable.", request)
        if not allowed:
            LOGGER.warning(
                "rate_limit_exceeded",
                path=request.url.path,
                client_ip=client_ip,
                limit=limit,
                correlation_id=_correlation_id(request),
            )
            return _error(429, "RATE_LIMITED", "Too many requests. Please try again shortly.", request)
        return await call_next(request)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject oversized request bodies before route parsing."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        max_body_size = settings.MAX_REQUEST_BODY_BYTES
        if request.url.path == "/api/admin/documents":
            # Multipart framing adds a small amount of metadata around the file.
            max_body_size = settings.ADMIN_UPLOAD_MAX_BYTES + (1024 * 1024)
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                body_size = int(content_length)
            except ValueError:
                return _error(400, "INVALID_REQUEST", "Invalid request headers.", request)
            if body_size > max_body_size:
                LOGGER.warning(
                    "request_body_too_large",
                    path=request.url.path,
                    body_size=body_size,
                    max_body_size=max_body_size,
                    correlation_id=_correlation_id(request),
                )
                return _error(413, "REQUEST_TOO_LARGE", "Request body is too large.", request)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach baseline browser security headers to API responses."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


class ProtectedRequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log protected API request outcomes without sensitive payloads."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        protected = request.url.path in settings.WIDGET_AUTH_PROTECTED_PATHS
        started = perf_counter()
        response = await call_next(request)
        if protected:
            widget_auth = getattr(request.state, "widget_auth", {}) or {}
            LOGGER.info(
                "protected_request_completed",
                correlation_id=_correlation_id(request),
                widget_id=widget_auth.get("widgetId"),
                session_id=widget_auth.get("sessionId"),
                origin=request.headers.get("origin") or widget_auth.get("origin"),
                path=request.url.path,
                status_code=response.status_code,
                latency_ms=round((perf_counter() - started) * 1000),
            )
        return response
