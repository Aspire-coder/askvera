"""Unit tests for session persistence and sliding expiration."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from services import session_service


def _engine_with_row(row):
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.first.return_value = row
    manager = MagicMock()
    manager.__enter__.return_value = connection
    engine = MagicMock()
    engine.begin.return_value = manager
    return engine, connection


def test_validate_and_touch_session_reuses_unexpired_session(monkeypatch) -> None:
    """An unexpired session is reused and receives sliding expiration."""
    now = datetime.now(UTC)
    engine, connection = _engine_with_row(
        {
            "session_id": "session-1",
            "created_at": now - timedelta(minutes=5),
            "expires_at": now + timedelta(minutes=30),
        }
    )
    monkeypatch.setattr(session_service, "get_engine", lambda: engine)

    assert session_service.validate_and_touch_session("session-1", "cid") is True
    assert connection.execute.call_count == 2


def test_validate_and_touch_session_rejects_missing_session(monkeypatch) -> None:
    """A missing session is treated as a new session that still requires consent."""
    engine, connection = _engine_with_row(None)
    monkeypatch.setattr(session_service, "get_engine", lambda: engine)

    assert session_service.validate_and_touch_session("new-session", "cid") is False
    assert connection.execute.call_count == 1


def test_validate_and_touch_session_rejects_expired_session(monkeypatch) -> None:
    """Expired sessions are not reused."""
    now = datetime.now(UTC)
    engine, connection = _engine_with_row(
        {
            "session_id": "session-1",
            "created_at": now - timedelta(minutes=5),
            "expires_at": now - timedelta(minutes=1),
        }
    )
    monkeypatch.setattr(session_service, "get_engine", lambda: engine)

    assert session_service.validate_and_touch_session("session-1", "cid") is False
    assert connection.execute.call_count == 1


def test_validate_and_touch_session_rejects_session_over_max_lifetime(monkeypatch) -> None:
    """Sessions beyond absolute max lifetime are renewed."""
    now = datetime.now(UTC)
    engine, connection = _engine_with_row(
        {
            "session_id": "session-1",
            "created_at": now - timedelta(days=8),
            "expires_at": now + timedelta(minutes=30),
        }
    )
    monkeypatch.setattr(session_service, "get_engine", lambda: engine)

    assert session_service.validate_and_touch_session("session-1", "cid") is False
    assert connection.execute.call_count == 1
