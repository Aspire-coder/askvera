"""Unit tests for session-level consent enforcement."""

from unittest.mock import MagicMock, patch

from fastapi.responses import JSONResponse

from api import routes
from services import consent_service
from utils.validators import ChatRequest, ConsentRequest


def _engine_with_row(row):
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.first.return_value = row
    manager = MagicMock()
    manager.__enter__.return_value = connection
    engine = MagicMock()
    engine.begin.return_value = manager
    return engine, connection


def test_has_valid_consent_returns_true_for_current_version(monkeypatch) -> None:
    """Consent is valid only when the session accepted the current legal version."""
    monkeypatch.setattr(consent_service.settings, "LEGAL_VERSION", "2026.1")
    engine, _connection = _engine_with_row({"consent_accepted": True, "consent_legal_version": "2026.1"})
    monkeypatch.setattr(consent_service, "get_engine", lambda: engine)

    assert consent_service.has_valid_consent("session-1", "cid") is True


def test_has_valid_consent_returns_false_for_missing_session(monkeypatch) -> None:
    """A missing session has no valid consent."""
    engine, _connection = _engine_with_row(None)
    monkeypatch.setattr(consent_service, "get_engine", lambda: engine)

    assert consent_service.has_valid_consent("missing-session", "cid") is False


def test_has_valid_consent_returns_false_for_wrong_version(monkeypatch) -> None:
    """Changing LEGAL_VERSION forces re-consent."""
    monkeypatch.setattr(consent_service.settings, "LEGAL_VERSION", "2026.2")
    engine, _connection = _engine_with_row({"consent_accepted": True, "consent_legal_version": "2026.1"})
    monkeypatch.setattr(consent_service, "get_engine", lambda: engine)

    assert consent_service.has_valid_consent("session-1", "cid") is False


def test_has_valid_consent_query_requires_unexpired_session(monkeypatch) -> None:
    """Expired sessions are not treated as consented sessions."""
    engine, connection = _engine_with_row(None)
    monkeypatch.setattr(consent_service, "get_engine", lambda: engine)

    assert consent_service.has_valid_consent("expired-session", "cid") is False
    query = str(connection.execute.call_args.args[0])
    assert "expires_at > now()" in query


def test_record_consent_writes_audit_and_session_hot_path(monkeypatch) -> None:
    """Consent acceptance writes consent_log and updates chat_sessions."""
    monkeypatch.setattr(consent_service.settings, "LEGAL_VERSION", "2026.1")
    engine, connection = _engine_with_row(None)
    monkeypatch.setattr(consent_service, "get_engine", lambda: engine)
    body = ConsentRequest(sessionId="session-1", country="US", lang="en", timestamp="2026-07-03T12:00:00Z", version="2026.1")

    consent_service.record_consent(body, "cid")

    assert connection.execute.call_count == 2
    consent_log_params = connection.execute.call_args_list[0].args[1]
    session_params = connection.execute.call_args_list[1].args[1]
    assert consent_log_params["session_id"] == "session-1"
    assert consent_log_params["country"] == "US"
    assert consent_log_params["lang"] == "en"
    assert consent_log_params["accepted_at"] == "2026-07-03T12:00:00Z"
    assert consent_log_params["version"] == "2026.1"
    assert consent_log_params["correlation_id"] == "cid"
    assert session_params["session_id"] == "session-1"
    assert session_params["version"] == "2026.1"
    assert session_params["accepted_at"] == "2026-07-03T12:00:00Z"


def test_chat_blocks_when_consent_missing() -> None:
    """The chat route returns 403 before calling expensive services."""
    request = MagicMock()
    request.state.correlation_id = "cid"
    body = ChatRequest(message="hello", sessionId="session-1", country="US", language="en")

    with (
        patch("api.routes.validate_and_touch_session", return_value=False),
        patch("api.routes.has_valid_consent", return_value=False),
        patch("api.routes.check_text") as check_text,
    ):
        response = routes.chat(body, request)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 403
    assert b"CONSENT_REQUIRED" in response.body
    check_text.assert_not_called()


def test_chat_blocks_when_consent_version_is_invalid() -> None:
    """A failed consent validation, including wrong legal version, blocks chat."""
    request = MagicMock()
    request.state.correlation_id = "cid"
    body = ChatRequest(message="hello", sessionId="session-1", country="US", language="en")

    with (
        patch("api.routes.validate_and_touch_session", return_value=True),
        patch("api.routes.has_valid_consent", return_value=False),
        patch("api.routes.retrieve_and_generate") as bedrock,
    ):
        response = routes.chat(body, request)

    assert response.status_code == 403
    assert b"CONSENT_REQUIRED" in response.body
    bedrock.assert_not_called()
