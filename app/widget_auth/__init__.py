"""Widget authentication package."""

from app.widget_registry.models import WidgetRegistration

from .models import WidgetAuthClaims, WidgetInitRequest, WidgetInitResponse, WidgetRefreshRequest, WidgetRefreshResponse
from .origin_validator import OriginValidation, is_origin_allowed, normalize_origin

__all__ = [
    "OriginValidation",
    "WidgetAuthClaims",
    "WidgetInitRequest",
    "WidgetInitResponse",
    "WidgetRefreshRequest",
    "WidgetRefreshResponse",
    "WidgetRegistration",
    "is_origin_allowed",
    "normalize_origin",
]
