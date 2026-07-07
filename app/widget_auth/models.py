"""Models for widget authentication."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator

from app.widget_registry.models import WidgetRegistration, WidgetStatus


class WidgetInitRequest(BaseModel):
    """Request body for POST /api/widget/init."""

    widgetId: str = Field(min_length=1, max_length=128)
    origin: str | None = Field(default=None, min_length=1, max_length=512)

    @field_validator("origin")
    @classmethod
    def normalize_origin(cls, value: str | None) -> str | None:
        """Normalize the client-provided origin for registry comparison."""
        if value is None:
            return None
        return value.strip().rstrip("/")


class WidgetAuthClaims(BaseModel):
    """Claims carried by short-lived widget JWTs."""

    iss: str
    aud: str
    sub: str
    widgetId: str
    organizationId: str
    companyName: str
    origin: str
    sessionId: str
    jti: str
    iat: int
    nbf: int
    exp: int


class WidgetRefreshRequest(BaseModel):
    """Request body for POST /api/widget/refresh."""

    token: str = Field(min_length=1)


class WidgetInitResponse(BaseModel):
    """Successful widget initialization payload."""

    token: str


class WidgetRefreshResponse(BaseModel):
    """Successful widget token refresh payload."""

    token: str
