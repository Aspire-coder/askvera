"""PostgreSQL consent_log write logic."""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from services.db import get_engine
from utils.exceptions import AwsServiceError
from utils.logging import get_logger
from utils.validators import ConsentRequest

LOGGER = get_logger("services.consent")


def record_consent(consent: ConsentRequest, correlation_id: str) -> None:
    """Write a privacy consent record to PostgreSQL."""
    try:
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO consent_log (session_id, country, lang, accepted_at, version)
                    VALUES (:session_id, :country, :lang, :accepted_at, :version)
                    """
                ),
                {
                    "session_id": consent.sessionId,
                    "country": consent.country,
                    "lang": consent.lang,
                    "accepted_at": consent.timestamp,
                    "version": consent.version,
                },
            )
    except SQLAlchemyError as exc:
        LOGGER.exception("consent_write_failed", correlation_id=correlation_id)
        raise AwsServiceError("Consent logging failed.") from exc
    LOGGER.info("consent_recorded", correlation_id=correlation_id, session_id=consent.sessionId, version=consent.version)
