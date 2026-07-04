"""Pydantic models for audit events."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from .enums import AuditEventType


class AuditEvent(BaseModel):
    """Structured event payload for future audit publishing."""

    event_id: str
    correlation_id: str

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    event_type: AuditEventType

    session_id: str | None = None
    visitor_id: str | None = None

    country: str | None = None
    language: str | None = None

    ip_address: str | None = None
    user_agent: str | None = None

    status: str

    latency_ms: int | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)
