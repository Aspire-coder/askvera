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
    return timedelta(seconds=settings.SESSION_TTL_SECONDS)


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
                    SELECT session_id, created_at, expires_at, ended_at
                    FROM chat_sessions
                    WHERE session_id = :session_id
                    """
                ),
                {"session_id": session_id},
            ).mappings().first()
            if not row:
                LOGGER.info("session_created", correlation_id=correlation_id, session_id=session_id)
                return False
            if row.get("ended_at") is not None or row["expires_at"] <= now or row["created_at"] <= max_created_at:
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


def can_resume_session(session_id: str, correlation_id: str = "widget-init") -> bool:
    """Return whether a browser may resume an existing open conversation."""
    if not session_id:
        return False
    try:
        with get_engine().begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT 1
                    FROM chat_sessions
                    WHERE session_id = :session_id
                      AND ended_at IS NULL
                      AND expires_at > now()
                      AND created_at > now() - (:max_days * interval '1 day')
                    """
                ),
                {"session_id": session_id, "max_days": settings.MAX_SESSION_DAYS},
            ).first()
    except SQLAlchemyError as exc:
        LOGGER.exception("session_resume_check_failed", correlation_id=correlation_id)
        raise AwsServiceError("Session resume check failed.") from exc
    return row is not None


def close_session(session_id: str, reason: str, correlation_id: str = "system") -> bool:
    """Close a conversation without deleting its transcript or consent audit."""
    try:
        with get_engine().begin() as connection:
            result = connection.execute(
                text(
                    """
                    UPDATE chat_sessions
                    SET ended_at = COALESCE(ended_at, now()),
                        end_reason = COALESCE(end_reason, :reason),
                        expires_at = LEAST(expires_at, now()),
                        updated_at = now()
                    WHERE session_id = :session_id
                    """
                ),
                {"session_id": session_id, "reason": reason},
            )
    except SQLAlchemyError as exc:
        LOGGER.exception("session_close_failed", correlation_id=correlation_id, session_id=session_id)
        raise AwsServiceError("Session close failed.") from exc
    closed = bool(result.rowcount)
    LOGGER.info("session_closed", correlation_id=correlation_id, session_id=session_id, reason=reason, found=closed)
    return closed
