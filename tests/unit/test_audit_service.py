"""Tests for legacy audit event mapping."""

from app.audit.enums import AuditEventType
from services.audit import _event_type


def test_semantic_shadow_has_a_dedicated_audit_type() -> None:
    assert _event_type("semantic_cache_shadow") is AuditEventType.SEMANTIC_CACHE_SHADOW
