"""Consent recording and session-level validation."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from services.db import get_engine
from utils.exceptions import AwsServiceError
from utils.logging import get_logger
from utils.validators import ConsentRequest

LOGGER = get_logger("services.consent_service")


def record_consent(consent: ConsentRequest, correlation_id: str) -> None:
    """Write consent metadata and mark the session as consented for the current legal version."""
    accepted_at = consent.timestamp or datetime.now(UTC).isoformat()
    expires_at = datetime.now(UTC) + timedelta(hours=settings.SESSION_TIMEOUT_HOURS)
    try:
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO consent_log (session_id, country, lang, accepted_at, version, accepted, correlation_id)
                    VALUES (:session_id, :country, :lang, :accepted_at, :version, true, :correlation_id)
                    """
                ),
                {
                    "session_id": consent.sessionId,
                    "country": consent.country,
                    "lang": consent.lang,
                    "accepted_at": accepted_at,
                    "version": settings.LEGAL_VERSION,
                    "correlation_id": correlation_id,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO chat_sessions (
                        session_id,
                        messages,
                        created_at,
                        last_activity_at,
                        expires_at,
                        updated_at,
                        consent_accepted,
                        consent_legal_version,
                        consent_accepted_at
                    )
                    VALUES (
                        :session_id,
                        '[]'::jsonb,
                        now(),
                        now(),
                        :expires_at,
                        now(),
                        true,
                        :version,
                        :accepted_at
                    )
                    ON CONFLICT (session_id)
                    DO UPDATE SET
                        consent_accepted = true,
                        consent_legal_version = EXCLUDED.consent_legal_version,
                        consent_accepted_at = EXCLUDED.consent_accepted_at,
                        last_activity_at = now(),
                        expires_at = GREATEST(chat_sessions.expires_at, EXCLUDED.expires_at),
                        updated_at = now()
                    """
                ),
                {
                    "session_id": consent.sessionId,
                    "expires_at": expires_at,
                    "version": settings.LEGAL_VERSION,
                    "accepted_at": accepted_at,
                },
            )
    except SQLAlchemyError as exc:
        LOGGER.exception("consent_write_failed", correlation_id=correlation_id)
        raise AwsServiceError("Consent logging failed.") from exc

    LOGGER.info(
        "consent_accepted",
        correlation_id=correlation_id,
        session_id=consent.sessionId,
        country=consent.country,
        language=consent.lang,
        version=settings.LEGAL_VERSION,
    )


def has_valid_consent(session_id: str, correlation_id: str = "system") -> bool:
    """Return true when the session accepted the current legal version."""
    try:
        with get_engine().begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT consent_accepted, consent_legal_version, expires_at
                    FROM chat_sessions
                    WHERE session_id = :session_id
                      AND expires_at > now()
                    """
                ),
                {"session_id": session_id},
            ).mappings().first()
    except SQLAlchemyError as exc:
        LOGGER.exception("consent_read_failed", correlation_id=correlation_id)
        raise AwsServiceError("Consent validation failed.") from exc

    is_valid = bool(row and row["consent_accepted"] is True and row["consent_legal_version"] == settings.LEGAL_VERSION)
    if not is_valid:
        LOGGER.warning(
            "consent_missing",
            correlation_id=correlation_id,
            session_id=session_id,
            expected_version=settings.LEGAL_VERSION,
        )
    return is_valid
