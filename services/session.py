"""PostgreSQL chat session management."""

import json
from threading import Lock
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from services.db import get_engine
from utils.exceptions import AwsServiceError
from utils.logging import get_logger

LOGGER = get_logger("services.session")
_MEMORY_LOCK = Lock()
_MEMORY_SESSIONS: dict[str, list[str]] = {}
SUPPORTED_CHAT_MEMORY_BACKENDS = {"postgres", "memory"}


def _max_history_messages() -> int:
    """Return a sane number of compact history messages to keep."""
    return max(2, int(settings.CHAT_HISTORY_MAX_MESSAGES))


def _use_memory_backend() -> bool:
    """Return true when chat history should stay in process memory."""
    backend = str(settings.CHAT_MEMORY_BACKEND or "postgres").lower()
    if backend not in SUPPORTED_CHAT_MEMORY_BACKENDS:
        LOGGER.warning("unsupported_chat_memory_backend", backend=backend, fallback="postgres")
        return False
    return backend == "memory"


def _coerce_messages(value: object) -> list[str]:
    """Normalize stored session messages into a compact string list."""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _format_history(messages: list[str]) -> str:
    """Render recent message history for the prompt."""
    return "\n".join(messages[-_max_history_messages():])


def _reset_memory_sessions() -> None:
    """Clear process-local chat history. Intended for tests and local demos."""
    with _MEMORY_LOCK:
        _MEMORY_SESSIONS.clear()


def _get_memory_history(session_id: str, correlation_id: str) -> str:
    with _MEMORY_LOCK:
        messages = list(_MEMORY_SESSIONS.get(session_id, []))
    LOGGER.info("session_loaded", correlation_id=correlation_id, session_id=session_id, message_count=len(messages))
    return _format_history(messages)


def _append_memory_turn(session_id: str, user_message: str, vera_response: str, correlation_id: str) -> None:
    turn = [f"user: {user_message}", f"vera: {vera_response}"]
    with _MEMORY_LOCK:
        _MEMORY_SESSIONS[session_id] = [*_MEMORY_SESSIONS.get(session_id, []), *turn][-_max_history_messages():]
    LOGGER.info("session_updated", correlation_id=correlation_id, session_id=session_id)


def get_session_history(session_id: str, correlation_id: str) -> str:
    """Load compact session history from PostgreSQL."""
    if _use_memory_backend():
        return _get_memory_history(session_id, correlation_id)

    try:
        with get_engine().begin() as connection:
            row = connection.execute(
                text("SELECT messages FROM chat_sessions WHERE session_id = :session_id"),
                {"session_id": session_id},
            ).mappings().first()
    except SQLAlchemyError as exc:
        LOGGER.exception("session_read_failed", correlation_id=correlation_id)
        raise AwsServiceError("Session read failed.") from exc
    messages = _coerce_messages(row["messages"] if row else [])
    LOGGER.info("session_loaded", correlation_id=correlation_id, session_id=session_id, message_count=len(messages))
    return _format_history(messages)


def append_session_turn(session_id: str, user_message: str, vera_response: str, correlation_id: str) -> None:
    """Append the latest turn to PostgreSQL session history."""
    if _use_memory_backend():
        _append_memory_turn(session_id, user_message, vera_response, correlation_id)
        return

    expires_at = datetime.now(UTC) + timedelta(seconds=settings.SESSION_TTL_SECONDS)
    turn = [f"user: {user_message}", f"vera: {vera_response}"]
    try:
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO chat_sessions (session_id, messages, expires_at, updated_at)
                    VALUES (:session_id, CAST(:messages AS jsonb), :expires_at, now())
                    ON CONFLICT (session_id)
                    DO UPDATE SET
                        messages = (
                            SELECT COALESCE(jsonb_agg(value ORDER BY ord), '[]'::jsonb)
                            FROM (
                                SELECT value, ord
                                FROM jsonb_array_elements(chat_sessions.messages || EXCLUDED.messages)
                                    WITH ORDINALITY AS items(value, ord)
                                ORDER BY ord DESC
                                LIMIT :max_messages
                            ) recent
                        ),
                        last_activity_at = now(),
                        expires_at = EXCLUDED.expires_at,
                        updated_at = now()
                    """
                ),
                {
                    "session_id": session_id,
                    "messages": json.dumps(turn),
                    "expires_at": expires_at,
                    "max_messages": _max_history_messages(),
                },
            )
    except SQLAlchemyError as exc:
        LOGGER.exception("session_write_failed", correlation_id=correlation_id)
        raise AwsServiceError("Session write failed.") from exc
    LOGGER.info("session_updated", correlation_id=correlation_id, session_id=session_id)


def cleanup_expired_sessions(correlation_id: str = "session-cleanup") -> int:
    """Delete sessions only after the configured transcript-retention period."""
    try:
        with get_engine().begin() as connection:
            result = connection.execute(
                text(
                    """
                    DELETE FROM chat_sessions
                    WHERE expires_at < now() - (:retention_days * interval '1 day')
                    """
                ),
                {"retention_days": settings.CHAT_TRANSCRIPT_RETENTION_DAYS},
            )
            deleted = int(result.rowcount or 0)
    except SQLAlchemyError as exc:
        LOGGER.exception("session_cleanup_failed", correlation_id=correlation_id)
        raise AwsServiceError("Expired session cleanup failed.") from exc
    LOGGER.info("session_cleanup_complete", correlation_id=correlation_id, deleted=deleted)
    return deleted
