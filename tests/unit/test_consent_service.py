"""Unit tests for session-level consent enforcement."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.responses import JSONResponse

from api import routes
from services import consent_service
from utils.exceptions import SessionExpiredError
from utils.validators import ChatRequest, ConsentRequest, EndSessionRequest


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


def test_record_consent_does_not_reopen_an_expired_session(monkeypatch) -> None:
    """Re-consent cannot turn an expired or explicitly closed chat active again."""
    engine, connection = _engine_with_row(None)
    connection.execute.side_effect = [MagicMock(rowcount=1), MagicMock(rowcount=0)]
    monkeypatch.setattr(consent_service, "get_engine", lambda: engine)
    body = ConsentRequest(sessionId="expired", country="US", lang="en", timestamp="2026-07-03T12:00:00Z", version="2026.1")

    with pytest.raises(SessionExpiredError):
        consent_service.record_consent(body, "cid")


def test_chat_blocks_when_session_is_not_active() -> None:
    """The chat route returns a stable expiry error before expensive services."""
    request = MagicMock()
    request.state.correlation_id = "cid"
    body = ChatRequest(message="hello", sessionId="session-1", country="US", language="en")

    with (
        patch("app.orchestrator.chat_orchestrator.validate_and_touch_session", return_value=False),
        patch("app.orchestrator.chat_orchestrator.has_valid_consent", return_value=False),
        patch("app.orchestrator.chat_orchestrator.ai_orchestrator.governance_engine.evaluate") as governance_evaluate,
    ):
        response = routes.chat(body, request)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 409
    assert b"SESSION_EXPIRED" in response.body
    governance_evaluate.assert_not_called()


def test_chat_blocks_when_consent_version_is_invalid() -> None:
    """A failed consent validation, including wrong legal version, blocks chat."""
    request = MagicMock()
    request.state.correlation_id = "cid"
    body = ChatRequest(message="hello", sessionId="session-1", country="US", language="en")

    with (
        patch("app.orchestrator.chat_orchestrator.validate_and_touch_session", return_value=True),
        patch("app.orchestrator.chat_orchestrator.has_valid_consent", return_value=False),
        patch("app.orchestrator.chat_orchestrator.ai_orchestrator.model_router.generate") as model_generate,
    ):
        response = routes.chat(body, request)

    assert response.status_code == 403
    assert b"CONSENT_REQUIRED" in response.body
    model_generate.assert_not_called()


def test_protected_request_cannot_use_another_session_id(monkeypatch) -> None:
    """The body session ID must match the authenticated widget token."""
    request = MagicMock()
    request.state.correlation_id = "cid"
    request.state.widget_auth = {"sessionId": "token-session"}
    monkeypatch.setattr(routes.settings, "WIDGET_AUTH_REQUIRED", True)
    body = ChatRequest(message="hello", sessionId="other-session", country="US", language="en")

    response = routes.chat(body, request)

    assert response.status_code == 403
    assert b"SESSION_MISMATCH" in response.body


def test_end_session_keeps_a_stable_api_contract(monkeypatch) -> None:
    """The lifecycle endpoint reports closure without deleting the transcript."""
    request = MagicMock()
    request.state.correlation_id = "cid"
    monkeypatch.setattr(routes.settings, "WIDGET_AUTH_REQUIRED", False)
    monkeypatch.setattr(routes, "close_session", lambda session_id, reason, *_: session_id == "session-1" and reason == "user_ended")

    response = routes.end_session(EndSessionRequest(sessionId="session-1", reason="user_ended"), request)

    assert response.success is True
    assert response.data == {"ended": True, "found": True, "reason": "user_ended"}
