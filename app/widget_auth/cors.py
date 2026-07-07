"""Dynamic CORS middleware for registered widget origins."""

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.widget_registry.service import widget_registry_service
from config import settings
from utils.logging import get_logger

from .origin_validator import is_origin_allowed, normalize_origin

LOGGER = get_logger("app.widget_auth.cors")


class DynamicWidgetCorsMiddleware(BaseHTTPMiddleware):
    """Allow browser requests from configured domains and active widget origins."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        origin = request.headers.get("origin")
        normalized_origin = normalize_origin(origin)
        origin_allowed = self._is_allowed_origin(normalized_origin)

        if request.method == "OPTIONS":
            response = Response(status_code=200 if origin_allowed else 400)
        else:
            response = await call_next(request)

        if origin_allowed:
            self._set_cors_headers(request, response, normalized_origin)

        return response

    def _is_allowed_origin(self, origin: str) -> bool:
        if not origin:
            return False

        try:
            allowed_origins = [*settings.ALLOWED_ORIGINS, *widget_registry_service.get_all_allowed_origins()]
        except Exception:
            LOGGER.exception("dynamic_cors_registry_lookup_failed", origin=origin)
            return False

        return is_origin_allowed(origin, allowed_origins).allowed

    def _set_cors_headers(self, request: Request, response: Response, origin: str) -> None:
        requested_headers = request.headers.get("access-control-request-headers")
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = requested_headers or "*"
        response.headers["Access-Control-Max-Age"] = "600"
        response.headers["Vary"] = "Origin"
