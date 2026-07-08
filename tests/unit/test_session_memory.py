"""Unit tests for optional in-memory chat history."""

from services import session


def test_memory_backend_stores_recent_chat_turns(monkeypatch) -> None:
    """In-memory chat history stores turns without touching PostgreSQL."""
    monkeypatch.setattr(session.settings, "CHAT_MEMORY_BACKEND", "memory")
    session._reset_memory_sessions()

    session.append_session_turn("session-1", "hello", "Hi there.", "cid")
    session.append_session_turn("session-1", "what about that?", "Here is the follow-up.", "cid")

    history = session.get_session_history("session-1", "cid")

    assert "user: hello" in history
    assert "vera: Hi there." in history
    assert "user: what about that?" in history
    assert "vera: Here is the follow-up." in history


def test_memory_backend_keeps_last_ten_messages(monkeypatch) -> None:
    """In-memory history keeps the same compact shape as PostgreSQL history."""
    monkeypatch.setattr(session.settings, "CHAT_MEMORY_BACKEND", "memory")
    monkeypatch.setattr(session.settings, "CHAT_HISTORY_MAX_MESSAGES", 10)
    session._reset_memory_sessions()

    for index in range(6):
        session.append_session_turn("session-1", f"user {index}", f"answer {index}", "cid")

    history = session.get_session_history("session-1", "cid")

    assert "user: user 0" not in history
    assert "vera: answer 0" not in history
    assert "user: user 1" in history
    assert "vera: answer 5" in history


def test_unsupported_memory_backend_falls_back_to_postgres(monkeypatch) -> None:
    """Unknown backends never silently switch production away from Postgres."""
    monkeypatch.setattr(session.settings, "CHAT_MEMORY_BACKEND", "unknown")

    assert session._use_memory_backend() is False


def test_history_limit_is_configurable(monkeypatch) -> None:
    """Local memory mode follows the shared configured history limit."""
    monkeypatch.setattr(session.settings, "CHAT_MEMORY_BACKEND", "memory")
    monkeypatch.setattr(session.settings, "CHAT_HISTORY_MAX_MESSAGES", 4)
    session._reset_memory_sessions()

    for index in range(3):
        session.append_session_turn("session-1", f"user {index}", f"answer {index}", "cid")

    history = session.get_session_history("session-1", "cid")

    assert "user: user 0" not in history
    assert "vera: answer 0" not in history
    assert "user: user 1" in history
    assert "vera: answer 2" in history
