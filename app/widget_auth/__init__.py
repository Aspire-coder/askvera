"""Widget authentication package."""

from .models import WidgetAuthClaims, WidgetInitRequest, WidgetInitResponse, WidgetRefreshRequest, WidgetRefreshResponse, WidgetRegistration
from .origin_validator import OriginValidation, is_origin_allowed, normalize_origin
from .service import WidgetAuthService, widget_auth_service

__all__ = [
    "OriginValidation",
    "WidgetAuthClaims",
    "WidgetAuthService",
    "WidgetInitRequest",
    "WidgetInitResponse",
    "WidgetRefreshRequest",
    "WidgetRefreshResponse",
    "WidgetRegistration",
    "is_origin_allowed",
    "normalize_origin",
    "widget_auth_service",
]
