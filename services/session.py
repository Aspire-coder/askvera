"""PostgreSQL chat session management."""

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from services.db import get_engine
from utils.exceptions import AwsServiceError
from utils.logging import get_logger

LOGGER = get_logger("services.session")


def get_session_history(session_id: str, correlation_id: str) -> str:
    """Load compact session history from PostgreSQL."""
    try:
        with get_engine().begin() as connection:
            row = connection.execute(
                text("SELECT messages FROM chat_sessions WHERE session_id = :session_id"),
                {"session_id": session_id},
            ).mappings().first()
    except SQLAlchemyError as exc:
        LOGGER.exception("session_read_failed", correlation_id=correlation_id)
        raise AwsServiceError("Session read failed.") from exc
    messages = list(row["messages"] if row else [])
    LOGGER.info("session_loaded", correlation_id=correlation_id, session_id=session_id, message_count=len(messages))
    return "\n".join(str(item) for item in messages[-10:])


def append_session_turn(session_id: str, user_message: str, vera_response: str, correlation_id: str) -> None:
    """Append the latest turn to PostgreSQL session history."""
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.SESSION_TTL_SECONDS)
    turn = [f"user: {user_message}", f"vera: {vera_response}"]
    try:
        with get_engine().begin() as connection:
            existing = connection.execute(
                text("SELECT messages FROM chat_sessions WHERE session_id = :session_id"),
                {"session_id": session_id},
            ).scalar_one_or_none()
            messages = [*(existing or []), *turn][-10:]
            connection.execute(
                text(
                    """
                    INSERT INTO chat_sessions (session_id, messages, expires_at, updated_at)
                    VALUES (:session_id, CAST(:messages AS jsonb), :expires_at, now())
                    ON CONFLICT (session_id)
                    DO UPDATE SET messages = EXCLUDED.messages, expires_at = EXCLUDED.expires_at, updated_at = now()
                    """
                ),
                {"session_id": session_id, "messages": json.dumps(messages), "expires_at": expires_at},
            )
    except SQLAlchemyError as exc:
        LOGGER.exception("session_write_failed", correlation_id=correlation_id)
        raise AwsServiceError("Session write failed.") from exc
    LOGGER.info("session_updated", correlation_id=correlation_id, session_id=session_id)


def cleanup_expired_sessions(correlation_id: str = "session-cleanup") -> int:
    """Delete expired chat sessions and return the number of removed rows."""
    try:
        with get_engine().begin() as connection:
            result = connection.execute(text("DELETE FROM chat_sessions WHERE expires_at < now()"))
            deleted = int(result.rowcount or 0)
    except SQLAlchemyError as exc:
        LOGGER.exception("session_cleanup_failed", correlation_id=correlation_id)
        raise AwsServiceError("Expired session cleanup failed.") from exc
    LOGGER.info("session_cleanup_complete", correlation_id=correlation_id, deleted=deleted)
    return deleted
