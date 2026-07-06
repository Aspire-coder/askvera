"""Models for widget authentication and registration."""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


WidgetStatus = Literal["active", "disabled"]


class WidgetRegistration(BaseModel):
    """A registered widget allowed to initialize authenticated sessions."""

    widgetId: str = Field(min_length=1, max_length=128)
    publishableKey: str = Field(min_length=1, max_length=256)
    organizationId: str = Field(min_length=1, max_length=128)
    companyName: str = Field(min_length=1, max_length=256)
    allowedOrigins: list[str] = Field(default_factory=list)
    status: WidgetStatus = "active"
    createdAt: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updatedAt: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("allowedOrigins")
    @classmethod
    def normalize_origins(cls, value: list[str]) -> list[str]:
        """Trim origin strings so comparisons are exact and predictable."""
        return [origin.strip().rstrip("/") for origin in value if origin.strip()]


class WidgetInitRequest(BaseModel):
    """Request body for POST /api/widget/init."""

    widgetId: str = Field(min_length=1, max_length=128)
    publishableKey: str = Field(min_length=1, max_length=256)
    origin: str = Field(min_length=1, max_length=512)

    @field_validator("origin")
    @classmethod
    def normalize_origin(cls, value: str) -> str:
        """Normalize the client-provided origin for registry comparison."""
        return value.strip().rstrip("/")


class WidgetAuthClaims(BaseModel):
    """Claims carried by short-lived widget JWTs."""

    widgetId: str
    organizationId: str
    companyName: str
    origin: str
    sessionId: str
    iat: int
    exp: int


class WidgetInitResponse(BaseModel):
    """Successful widget initialization payload."""

    token: str
    expiresIn: int
    sessionId: str
    widgetId: str
    organizationId: str
    companyName: str
