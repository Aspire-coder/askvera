"""Pydantic models for API request and response validation."""

from datetime import UTC, datetime
from typing import Any

import re

from pydantic import BaseModel, Field, field_validator, model_validator

from config.vera_persona import ROLE_CONTENT_SCOPES
from services.market_config import get_country_codes, get_language_codes_for_country

TRAFFIC_SOURCES = {"widget", "evaluation", "backend_test", "admin_test"}


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
    trafficSource: str = Field(default="widget", max_length=32)

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

    @field_validator("trafficSource")
    @classmethod
    def validate_traffic_source(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in TRAFFIC_SOURCES:
            raise ValueError("Unsupported traffic source.")
        return normalized

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


class EndSessionRequest(BaseModel):
    """Request to close a chat while retaining its audit records."""

    sessionId: str = Field(min_length=1, max_length=128)
    reason: str = Field(default="user_ended", pattern="^(user_ended|new_chat|idle_timeout)$")


class FeedbackRequest(BaseModel):
    """Validated feedback queue body."""

    sessionId: str
    messageId: str
    rating: int = Field(ge=-1, le=1)
    comment: str = Field(default="", max_length=2000)
    requestType: str = Field(default="feedback", pattern="^(feedback|support)$")
    metadata: dict[str, Any] = Field(default_factory=dict)


class SupportRequest(BaseModel):
    """Validated customer support handoff request."""

    sessionId: str = Field(min_length=1, max_length=128)
    messageId: str = Field(default="", max_length=128)
    firstName: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=254)
    question: str = Field(min_length=1, max_length=4000)
    country: str = Field(min_length=2, max_length=64)
    language: str = Field(min_length=2, max_length=16)

    @field_validator("firstName", "question")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field is required.")
        return normalized

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "\r" in normalized or "\n" in normalized or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized

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

    @model_validator(mode="after")
    def validate_locale_pair(self) -> "SupportRequest":
        if self.language not in _language_codes_for_country(self.country):
            raise ValueError("Unsupported language for country.")
        return self
