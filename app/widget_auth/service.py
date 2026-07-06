"""Widget registry validation and token issuing."""

from __future__ import annotations

import json
from time import time
from uuid import uuid4

from config import settings
from utils.exceptions import AskVeraError
from utils.logging import get_logger

from .jwt import encode_widget_token
from .models import WidgetAuthClaims, WidgetInitRequest, WidgetInitResponse, WidgetRegistration

LOGGER = get_logger("app.widget_auth.service")


class WidgetAuthError(AskVeraError):
    """Raised when widget initialization fails."""

    status_code = 403
    error_code = "WIDGET_AUTH_FAILED"

    def __init__(self, message: str = "Widget authentication failed.") -> None:
        super().__init__(message)


def _load_registry() -> dict[str, WidgetRegistration]:
    """Load widget registrations from configuration."""
    try:
        raw_registrations = json.loads(settings.WIDGET_REGISTRY_JSON or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError("WIDGET_REGISTRY_JSON must be valid JSON.") from exc

    registrations = [WidgetRegistration.model_validate(item) for item in raw_registrations]
    return {registration.widgetId: registration for registration in registrations}


class WidgetAuthService:
    """Validate widget initialization requests and issue short-lived JWTs."""

    def __init__(self) -> None:
        self._registry = _load_registry()

    def reload(self) -> None:
        """Reload registry entries from settings, useful after SSM startup config."""
        self._registry = _load_registry()

    def get_registration(self, widget_id: str) -> WidgetRegistration | None:
        """Return a widget registration by ID."""
        return self._registry.get(widget_id)

    def validate_origin(self, registration: WidgetRegistration, origin: str) -> bool:
        """Return True if the origin is exactly allowed for this widget."""
        normalized_origin = origin.strip().rstrip("/")
        return normalized_origin in registration.allowedOrigins

    def initialize(self, request: WidgetInitRequest, correlation_id: str) -> WidgetInitResponse:
        """Validate widget credentials and issue a short-lived widget JWT."""
        registration = self.get_registration(request.widgetId)
        if registration is None:
            LOGGER.warning("widget_auth_unknown_widget", correlation_id=correlation_id, widget_id=request.widgetId)
            raise WidgetAuthError()

        if registration.status != "active":
            LOGGER.warning("widget_auth_disabled_widget", correlation_id=correlation_id, widget_id=request.widgetId)
            raise WidgetAuthError()

        if not hmac_safe_equal(registration.publishableKey, request.publishableKey):
            LOGGER.warning("widget_auth_key_mismatch", correlation_id=correlation_id, widget_id=request.widgetId)
            raise WidgetAuthError()

        if not self.validate_origin(registration, request.origin):
            LOGGER.warning(
                "widget_auth_origin_denied",
                correlation_id=correlation_id,
                widget_id=request.widgetId,
                origin=request.origin,
            )
            raise WidgetAuthError()

        issued_at = int(time())
        session_id = str(uuid4())
        expires_at = issued_at + settings.WIDGET_JWT_TTL_SECONDS
        claims = WidgetAuthClaims(
            widgetId=registration.widgetId,
            organizationId=registration.organizationId,
            companyName=registration.companyName,
            origin=request.origin,
            sessionId=session_id,
            iat=issued_at,
            exp=expires_at,
        )
        LOGGER.info("widget_auth_initialized", correlation_id=correlation_id, widget_id=registration.widgetId, origin=request.origin)
        return WidgetInitResponse(
            token=encode_widget_token(claims.model_dump()),
            expiresIn=settings.WIDGET_JWT_TTL_SECONDS,
            sessionId=session_id,
            widgetId=registration.widgetId,
            organizationId=registration.organizationId,
            companyName=registration.companyName,
        )


def hmac_safe_equal(left: str, right: str) -> bool:
    """Compare public keys without leaking timing information."""
    import hmac

    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


widget_auth_service = WidgetAuthService()
