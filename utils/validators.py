"""Pydantic models for API request and response validation."""

from datetime import UTC, datetime
from typing import Any

import re

from pydantic import BaseModel, Field, field_validator, model_validator

from config.vera_persona import ROLE_CONTENT_SCOPES
from services.market_config import get_country_codes, get_supported_language_codes

TRAFFIC_SOURCES = {"widget", "evaluation", "backend_test", "admin_test"}


def _country_codes() -> set[str]:
    return get_country_codes()


def _supported_language_codes() -> set[str]:
    """Languages a reply may be written in, on any market.

    Response language is deliberately decoupled from document authority. A
    Germany-selected reader asking in English was previously rejected outright by
    request validation, which is the language-and-market failure recorded in the
    2026-09-07 comparison. Answering in English does NOT authorise US policy as a
    substitute for German evidence: the selected market still governs which
    documents are eligible, enforced in retrieval and evidence approval.
    """
    return get_supported_language_codes()


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
        if self.language not in _supported_language_codes():
            raise ValueError("Unsupported language.")
        return self


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
        # Must accept the same languages as ChatRequest: a reader offered a
        # language for chat has to be able to consent in it. Consent copy exists
        # for every configured language.
        if self.lang not in _supported_language_codes():
            raise ValueError("Unsupported language.")
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
    expected_answer: str | None = None
    requestType: str = Field(default="feedback", pattern="^(feedback|support)$")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("expected_answer")
    @classmethod
    def truncate_expected_answer(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized[:2000] or None


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
        if self.language not in _supported_language_codes():
            raise ValueError("Unsupported language.")
        return self
