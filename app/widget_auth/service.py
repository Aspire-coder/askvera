"""Widget registry validation and token issuing."""

from __future__ import annotations

from time import time
from uuid import uuid4

from config import settings
from app.widget_registry.service import WidgetRegistryService, widget_registry_service
from utils.exceptions import AskVeraError
from utils.logging import get_logger

from .jwt import WidgetTokenError, decode_widget_token, encode_widget_token, revoke_widget_token_id
from .models import WidgetAuthClaims, WidgetInitRequest, WidgetInitResponse, WidgetRefreshResponse, WidgetRegistration
from .origin_validator import is_origin_allowed

LOGGER = get_logger("app.widget_auth.service")


class WidgetAuthError(AskVeraError):
    """Raised when widget initialization fails."""

    status_code = 403
    error_code = "WIDGET_AUTH_FAILED"

    def __init__(self, message: str = "Widget authentication failed.") -> None:
        super().__init__(message)


class WidgetAuthService:
    """Validate widget initialization requests and issue short-lived JWTs."""

    def __init__(self, registry_service: WidgetRegistryService | None = None) -> None:
        self._registry_service = registry_service or widget_registry_service

    def reload(self) -> None:
        """Reload registry entries from settings, useful after SSM startup config."""
        self._registry_service.reload()

    def get_registration(self, widget_id: str) -> WidgetRegistration | None:
        """Return a widget registration by ID."""
        return self._registry_service.get_widget(widget_id)

    def validate_origin(self, registration: WidgetRegistration, origin: str | None) -> bool:
        """Return True if the origin is allowed for this widget."""
        return is_origin_allowed(origin, registration.allowedOrigins).allowed

    def _build_claims(self, registration: WidgetRegistration, origin: str, session_id: str) -> WidgetAuthClaims:
        issued_at = int(time())
        return WidgetAuthClaims(
            iss=settings.WIDGET_JWT_ISSUER,
            aud=settings.WIDGET_JWT_AUDIENCE,
            sub="widget-session",
            widgetId=registration.widgetId,
            organizationId=registration.organizationId,
            companyName=registration.companyName,
            origin=origin,
            sessionId=session_id,
            jti=str(uuid4()),
            iat=issued_at,
            nbf=issued_at,
            exp=issued_at + settings.WIDGET_JWT_TTL_SECONDS,
        )

    def _response_from_claims(self, claims: WidgetAuthClaims) -> WidgetInitResponse:
        return WidgetInitResponse(
            token=encode_widget_token(claims.model_dump()),
        )

    def initialize(self, request: WidgetInitRequest, correlation_id: str, client_ip: str | None = None) -> WidgetInitResponse:
        """Validate widget credentials and issue a short-lived widget JWT."""
        registration = self.get_registration(request.widgetId)
        if registration is None:
            LOGGER.warning("widget_auth_unknown_widget", correlation_id=correlation_id, widget_id=request.widgetId)
            raise WidgetAuthError()

        if registration.status != "active":
            LOGGER.warning("widget_auth_disabled_widget", correlation_id=correlation_id, widget_id=request.widgetId)
            raise WidgetAuthError()

        origin_validation = is_origin_allowed(request.origin, registration.allowedOrigins)
        if not origin_validation.allowed:
            LOGGER.warning(
                "widget_auth_origin_denied",
                correlation_id=correlation_id,
                widget_id=request.widgetId,
                origin=request.origin,
                ip_address=client_ip,
                reason=origin_validation.reason,
            )
            raise WidgetAuthError()

        session_id = str(uuid4())
        claims = self._build_claims(registration, origin_validation.normalized_origin, session_id)
        LOGGER.info(
            "widget_auth_initialized",
            correlation_id=correlation_id,
            widget_id=registration.widgetId,
            origin=origin_validation.normalized_origin,
            session_id=session_id,
            token_id=claims.jti,
        )
        return self._response_from_claims(claims)

    def refresh(self, token: str, correlation_id: str, request_origin: str | None = None) -> WidgetRefreshResponse:
        """Validate an existing widget token and issue a fresh token."""
        try:
            existing_claims = decode_widget_token(token)
        except WidgetTokenError:
            LOGGER.warning("widget_auth_refresh_token_rejected", correlation_id=correlation_id)
            raise

        registration = self.get_registration(str(existing_claims.get("widgetId", "")))
        if registration is None or registration.status != "active":
            LOGGER.warning(
                "widget_auth_refresh_inactive_widget",
                correlation_id=correlation_id,
                widget_id=existing_claims.get("widgetId"),
                session_id=existing_claims.get("sessionId"),
            )
            raise WidgetAuthError()

        token_origin = str(existing_claims.get("origin", ""))
        if request_origin and request_origin.rstrip("/") != token_origin:
            LOGGER.warning(
                "widget_auth_refresh_origin_mismatch",
                correlation_id=correlation_id,
                widget_id=registration.widgetId,
                origin=request_origin,
                token_origin=token_origin,
                session_id=existing_claims.get("sessionId"),
            )
            raise WidgetAuthError()

        origin_validation = is_origin_allowed(token_origin, registration.allowedOrigins)
        if not origin_validation.allowed:
            LOGGER.warning(
                "widget_auth_refresh_origin_denied",
                correlation_id=correlation_id,
                widget_id=registration.widgetId,
                origin=token_origin,
                reason=origin_validation.reason,
                session_id=existing_claims.get("sessionId"),
            )
            raise WidgetAuthError()

        revoke_widget_token_id(str(existing_claims.get("jti", "")))
        claims = self._build_claims(registration, origin_validation.normalized_origin, str(existing_claims.get("sessionId", "")))
        LOGGER.info(
            "widget_auth_token_refreshed",
            correlation_id=correlation_id,
            widget_id=registration.widgetId,
            session_id=claims.sessionId,
            token_id=claims.jti,
        )
        response = self._response_from_claims(claims)
        return WidgetRefreshResponse(**response.model_dump())

widget_auth_service = WidgetAuthService()
