"""Session lifecycle helpers for persistence and sliding expiration."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from services.db import get_engine
from utils.exceptions import AwsServiceError
from utils.logging import get_logger

LOGGER = get_logger("services.session_service")


def session_timeout_delta() -> timedelta:
    """Return the configured inactivity timeout."""
    return timedelta(hours=settings.SESSION_TIMEOUT_HOURS)


def max_session_lifetime_delta() -> timedelta:
    """Return the configured absolute session lifetime."""
    return timedelta(days=settings.MAX_SESSION_DAYS)


def validate_and_touch_session(session_id: str, correlation_id: str = "system") -> bool:
    """Validate an existing session and extend its inactivity timeout."""
    now = datetime.now(UTC)
    next_expiry = now + session_timeout_delta()
    max_created_at = now - max_session_lifetime_delta()
    try:
        with get_engine().begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT session_id, created_at, expires_at
                    FROM chat_sessions
                    WHERE session_id = :session_id
                    """
                ),
                {"session_id": session_id},
            ).mappings().first()
            if not row:
                LOGGER.info("session_created", correlation_id=correlation_id, session_id=session_id)
                return False
            if row["expires_at"] <= now or row["created_at"] <= max_created_at:
                LOGGER.info("session_expired", correlation_id=correlation_id, session_id=session_id)
                return False
            connection.execute(
                text(
                    """
                    UPDATE chat_sessions
                    SET last_activity_at = now(),
                        expires_at = :expires_at,
                        updated_at = now()
                    WHERE session_id = :session_id
                    """
                ),
                {"session_id": session_id, "expires_at": next_expiry},
            )
    except SQLAlchemyError as exc:
        LOGGER.exception("session_validation_failed", correlation_id=correlation_id)
        raise AwsServiceError("Session validation failed.") from exc
    LOGGER.info("session_reused", correlation_id=correlation_id, session_id=session_id)
    return True
