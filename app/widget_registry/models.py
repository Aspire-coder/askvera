"""Models for registered customer widgets."""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


WidgetStatus = Literal["active", "disabled"]


class WidgetRegistration(BaseModel):
    """A registered widget allowed to initialize authenticated sessions."""

    widgetId: str = Field(min_length=1, max_length=128)
    organizationId: str = Field(min_length=1, max_length=128)
    companyName: str = Field(min_length=1, max_length=256)
    allowedOrigins: list[str] = Field(default_factory=list)
    status: WidgetStatus = "active"
    createdAt: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updatedAt: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    version: int = 1
    sdkVersion: str | None = None
    legalVersion: str | None = None
    environment: str | None = None
    createdBy: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("allowedOrigins")
    @classmethod
    def normalize_origins(cls, value: list[str]) -> list[str]:
        """Trim origin strings so comparisons are exact and predictable."""
        return [origin.strip().rstrip("/") for origin in value if origin.strip()]
