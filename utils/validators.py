"""Pydantic models for API request and response validation."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from config.vera_persona import ROLE_CONTENT_SCOPES
from services.market_config import get_country_codes, get_language_codes_for_country


def _country_codes() -> set[str]:
    return get_country_codes()


def _language_codes_for_country(country_code: str) -> set[str]:
    return get_language_codes_for_country(country_code)


class Envelope(BaseModel):
    """Standard success or error response envelope."""

    success: bool
    data: dict[str, Any] | None = None
    error: dict[str, str] | None = None
    correlationId: str
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ChatRequest(BaseModel):
    """Validated /api/chat request body."""

    message: str = Field(min_length=1, max_length=4000)
    sessionId: str = Field(min_length=1, max_length=128)
    country: str = Field(min_length=2, max_length=64)
    language: str = Field(min_length=2, max_length=16)
    role: str = Field(default="new_prospect", max_length=64)

    @field_validator("country")
    @classmethod
    def validate_country(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in _country_codes():
            raise ValueError("Unsupported country.")
        return normalized

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        return value.lower()

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in ROLE_CONTENT_SCOPES:
            raise ValueError("Unsupported role.")
        return value

    @model_validator(mode="after")
    def validate_locale_pair(self) -> "ChatRequest":
        if self.language not in _language_codes_for_country(self.country):
            raise ValueError("Unsupported language for country.")
        return self


class Source(BaseModel):
    """Source citation returned to the widget."""

    title: str
    uri: str
    excerpt: str = ""


class ChatData(BaseModel):
    """Successful chat response data."""

    response: str
    sources: list[Source]
    confidence: float
    correlationId: str


class ConsentRequest(BaseModel):
    """Validated consent logging body."""

    sessionId: str
    country: str
    lang: str
    timestamp: str
    version: str

    @field_validator("country")
    @classmethod
    def validate_country(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in _country_codes():
            raise ValueError("Unsupported country.")
        return normalized

    @field_validator("lang")
    @classmethod
    def validate_language(cls, value: str) -> str:
        return value.lower()

    @model_validator(mode="after")
    def validate_locale_pair(self) -> "ConsentRequest":
        if self.lang not in _language_codes_for_country(self.country):
            raise ValueError("Unsupported language for country.")
        return self


class FeedbackRequest(BaseModel):
    """Validated feedback queue body."""

    sessionId: str
    messageId: str
    rating: int = Field(ge=-1, le=1)
    comment: str = Field(default="", max_length=2000)
