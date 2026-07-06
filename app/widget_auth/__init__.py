"""Widget authentication package."""

from .models import WidgetAuthClaims, WidgetInitRequest, WidgetInitResponse, WidgetRegistration
from .service import WidgetAuthService, widget_auth_service

__all__ = [
    "WidgetAuthClaims",
    "WidgetAuthService",
    "WidgetInitRequest",
    "WidgetInitResponse",
    "WidgetRegistration",
    "widget_auth_service",
]
