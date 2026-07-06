"""FastAPI middleware that protects widget API endpoints."""

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings
from utils.logging import get_logger
from utils.validators import Envelope

from .jwt import WidgetTokenError, decode_widget_token
from .origin_validator import is_origin_allowed, normalize_origin
from .service import widget_auth_service

LOGGER = get_logger("app.widget_auth.middleware")


def _correlation_id(request: Request) -> str:
    return str(getattr(request.state, "correlation_id", "system"))


def _unauthorized(correlation_id: str, message: str = "A valid widget session token is required.") -> JSONResponse:
    envelope = Envelope(
        success=False,
        error={"code": "WIDGET_AUTH_REQUIRED", "message": message},
        correlationId=correlation_id,
    )
    return JSONResponse(status_code=401, content=envelope.model_dump())


class WidgetAuthMiddleware(BaseHTTPMiddleware):
    """Require a valid widget JWT for protected API paths when enabled."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if not settings.WIDGET_AUTH_REQUIRED or request.url.path not in settings.WIDGET_AUTH_PROTECTED_PATHS:
            return await call_next(request)

        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return _unauthorized(_correlation_id(request))

        token = authorization.removeprefix("Bearer ").strip()
        try:
            claims = decode_widget_token(token)
        except WidgetTokenError:
            LOGGER.warning("widget_auth_token_invalid", correlation_id=_correlation_id(request), path=request.url.path)
            return _unauthorized(_correlation_id(request))

        registration = widget_auth_service.get_registration(str(claims.get("widgetId", "")))
        if registration is None or registration.status != "active":
            return _unauthorized(_correlation_id(request), "Widget is not active.")

        origin = str(claims.get("origin", ""))
        request_origin = request.headers.get("origin")
        if request_origin and normalize_origin(request_origin) != normalize_origin(origin):
            LOGGER.warning(
                "widget_auth_token_origin_mismatch",
                correlation_id=_correlation_id(request),
                widget_id=registration.widgetId,
                origin=request_origin,
                token_origin=origin,
                path=request.url.path,
            )
            return _unauthorized(_correlation_id(request), "Widget origin is not allowed.")

        origin_validation = is_origin_allowed(origin, registration.allowedOrigins)
        if not origin_validation.allowed:
            LOGGER.warning(
                "widget_auth_token_origin_denied",
                correlation_id=_correlation_id(request),
                widget_id=registration.widgetId,
                origin=origin,
                reason=origin_validation.reason,
                path=request.url.path,
            )
            return _unauthorized(_correlation_id(request), "Widget origin is not allowed.")

        request.state.widget_auth = claims
        return await call_next(request)
