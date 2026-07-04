"""Audit event type definitions."""

from enum import Enum


class AuditEventType(str, Enum):
    """Supported ASK Vera audit event types."""

    HTTP_REQUEST = "HTTP_REQUEST"

    CHAT_REQUEST = "CHAT_REQUEST"
    CHAT_RESPONSE = "CHAT_RESPONSE"

    CONSENT_ACCEPTED = "CONSENT_ACCEPTED"
    CONSENT_REJECTED = "CONSENT_REJECTED"

    SESSION_CREATED = "SESSION_CREATED"
    SESSION_EXPIRED = "SESSION_EXPIRED"

    CACHE_HIT = "CACHE_HIT"
    CACHE_MISS = "CACHE_MISS"

    ERROR = "ERROR"

    STARTUP = "STARTUP"
