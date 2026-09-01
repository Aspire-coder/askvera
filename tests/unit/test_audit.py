"""Tests for non-blocking audit delivery."""

from unittest.mock import AsyncMock

from services import audit


def test_audit_failure_does_not_fail_the_customer_path(monkeypatch) -> None:
    publisher = AsyncMock(side_effect=RuntimeError("audit unavailable"))
    monkeypatch.setattr(audit, "publish_audit_event", publisher)

    audit.write_audit_event({"type": "chat", "country": "US"}, "cid")

    publisher.assert_awaited_once()
