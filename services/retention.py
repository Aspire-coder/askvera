"""Independent retention policies for operational PostgreSQL data."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from services.db import get_engine
from utils.exceptions import AwsServiceError
from utils.logging import get_logger

LOGGER = get_logger("services.retention")


@dataclass(frozen=True)
class RetentionRule:
    table: str
    timestamp_column: str
    days_setting: str
    predicate: str = ""


RETENTION_RULES = (
    RetentionRule("retrieval_shadow_comparisons", "created_at", "RETRIEVAL_SHADOW_RETENTION_DAYS"),
    RetentionRule("chat_analytics", "created_at", "CHAT_ANALYTICS_RETENTION_DAYS"),
    RetentionRule("feedback_events", "created_at", "FEEDBACK_RETENTION_DAYS"),
    RetentionRule("support_requests", "created_at", "SUPPORT_REQUEST_RETENTION_DAYS"),
    RetentionRule(
        "ingestion_jobs",
        "updated_at",
        "INGESTION_JOB_RETENTION_DAYS",
        "AND status IN ('completed', 'failed', 'cancelled')",
    ),
    RetentionRule("consent_log", "created_at", "CONSENT_LOG_RETENTION_DAYS"),
)


def _retention_days(setting_name: str) -> int:
    value = int(getattr(settings, setting_name))
    if value < 1:
        raise ValueError(f"{setting_name} must be at least 1 day.")
    return value


def _selected_rules(category: str | None) -> tuple[RetentionRule, ...]:
    rules = (*RETENTION_RULES, RetentionRule("chat_sessions", "expires_at", "CHAT_TRANSCRIPT_RETENTION_DAYS"))
    if not category:
        return rules
    selected = tuple(rule for rule in rules if rule.table == category)
    if not selected:
        raise ValueError(f"Unknown retention category: {category}")
    return selected


def preview_retained_data(
    *,
    category: str | None = None,
    correlation_id: str = "retention-preview",
) -> dict[str, int]:
    """Count expired records without changing operational data."""
    counts: dict[str, int] = {}
    try:
        with get_engine().begin() as connection:
            for rule in _selected_rules(category):
                row = connection.execute(
                    text(
                        f"""
                        SELECT count(*) AS count
                        FROM {rule.table}
                        WHERE {rule.timestamp_column} < now() - (:retention_days * interval '1 day')
                        {rule.predicate}
                        """
                    ),
                    {"retention_days": _retention_days(rule.days_setting)},
                ).mappings().first()
                counts[rule.table] = int((row or {}).get("count", 0))
    except (SQLAlchemyError, ValueError) as exc:
        LOGGER.exception("retention_preview_failed", correlation_id=correlation_id)
        raise AwsServiceError("Operational data retention preview failed.") from exc
    LOGGER.info("retention_preview_complete", correlation_id=correlation_id, counts=counts)
    return counts


def cleanup_retained_data(
    correlation_id: str = "retention-cleanup",
    *,
    category: str | None = None,
    batch_size: int = 1_000,
) -> dict[str, int]:
    """Delete expired operational records in bounded batches."""
    if batch_size < 1 or batch_size > 10_000:
        raise AwsServiceError("Retention batch size must be between 1 and 10000.")
    deleted: dict[str, int] = {}
    try:
        for rule in _selected_rules(category):
            deleted[rule.table] = 0
            while True:
                with get_engine().begin() as connection:
                    result = connection.execute(
                        text(
                            f"""
                            WITH expired AS (
                                SELECT ctid
                                FROM {rule.table}
                                WHERE {rule.timestamp_column} < now() - (:retention_days * interval '1 day')
                                {rule.predicate}
                                LIMIT :batch_size
                            )
                            DELETE FROM {rule.table}
                            WHERE ctid IN (SELECT ctid FROM expired)
                            """
                        ),
                        {
                            "retention_days": _retention_days(rule.days_setting),
                            "batch_size": batch_size,
                        },
                    )
                batch_deleted = int(result.rowcount or 0)
                deleted[rule.table] += batch_deleted
                if batch_deleted < batch_size:
                    break
    except (SQLAlchemyError, ValueError) as exc:
        LOGGER.exception("retention_cleanup_failed", correlation_id=correlation_id)
        raise AwsServiceError("Operational data retention cleanup failed.") from exc

    LOGGER.info(
        "retention_cleanup_complete",
        correlation_id=correlation_id,
        deleted=deleted,
        category=category or "all",
        batch_size=batch_size,
    )
    return deleted
