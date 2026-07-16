"""Operational analytics persistence and queries for AskVera administrators."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.response.models import ChatResponse
from services.db import get_engine
from utils.redaction import redact_common_pii
from utils.logging import get_logger
from utils.validators import ChatRequest, FeedbackRequest

LOGGER = get_logger("services.analytics")


def _token_counts(response: ChatResponse) -> tuple[int, int]:
    usage = response.metadata.get("token_usage") if response.metadata else None
    if not isinstance(usage, dict):
        return 0, 0
    input_tokens = usage.get("inputTokens", usage.get("input_tokens", 0))
    output_tokens = usage.get("outputTokens", usage.get("output_tokens", 0))
    try:
        return int(input_tokens or 0), int(output_tokens or 0)
    except (TypeError, ValueError):
        return 0, 0


def _topic(response: ChatResponse) -> str:
    if response.citations:
        first = response.citations[0]
        return str(first.get("sectionTitle") or first.get("title") or "Knowledge answer")[:160]
    if response.metadata.get("failure_layer"):
        return "Unanswered / needs review"
    return "General assistance"


def record_chat_interaction(body: ChatRequest, response: ChatResponse, correlation_id: str) -> None:
    """Persist a scrubbed chat outcome for aggregate analytics and QA review."""
    input_tokens, output_tokens = _token_counts(response)
    try:
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO chat_analytics (
                        correlation_id, session_id, country, language, question,
                        answer, topic, confidence, source_count, input_tokens,
                        output_tokens, fallback, failure_layer, created_at
                    ) VALUES (
                        :correlation_id, :session_id, :country, :language, :question,
                        :answer, :topic, :confidence, :source_count, :input_tokens,
                        :output_tokens, :fallback, :failure_layer, now()
                    )
                    ON CONFLICT (correlation_id) DO UPDATE SET
                        answer = EXCLUDED.answer,
                        confidence = EXCLUDED.confidence,
                        source_count = EXCLUDED.source_count,
                        input_tokens = EXCLUDED.input_tokens,
                        output_tokens = EXCLUDED.output_tokens,
                        fallback = EXCLUDED.fallback,
                        failure_layer = EXCLUDED.failure_layer
                    """
                ),
                {
                    "correlation_id": correlation_id,
                    "session_id": body.sessionId,
                    "country": body.country,
                    "language": body.language,
                    "question": redact_common_pii(" ".join(body.message.split()))[:4000],
                    "answer": response.answer[:12_000],
                    "topic": _topic(response),
                    "confidence": float(response.confidence or 0.0),
                    "source_count": len(response.citations),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "fallback": bool(response.metadata.get("fallback")),
                    "failure_layer": str(response.metadata.get("failure_layer") or ""),
                },
            )
    except SQLAlchemyError:
        LOGGER.exception("chat_analytics_write_failed", correlation_id=correlation_id)


def record_feedback_event(feedback: FeedbackRequest, correlation_id: str) -> None:
    """Persist feedback for direct admin drill-down while retaining SQS delivery."""
    metadata = feedback.metadata or {}
    linked_correlation_id = str(metadata.get("correlationId") or metadata.get("correlation_id") or "")
    try:
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO feedback_events (
                        event_id, correlation_id, session_id, message_id, rating,
                        comment, request_type, country, language, created_at
                    ) VALUES (
                        :event_id, :correlation_id, :session_id, :message_id, :rating,
                        :comment, :request_type, :country, :language, now()
                    )
                    ON CONFLICT (event_id) DO NOTHING
                    """
                ),
                {
                    "event_id": correlation_id,
                    "correlation_id": linked_correlation_id,
                    "session_id": feedback.sessionId,
                    "message_id": feedback.messageId,
                    "rating": feedback.rating,
                    "comment": feedback.comment,
                    "request_type": feedback.requestType,
                    "country": str(metadata.get("country") or ""),
                    "language": str(metadata.get("language") or ""),
                },
            )
    except SQLAlchemyError:
        LOGGER.exception("feedback_analytics_write_failed", correlation_id=correlation_id)


def analytics_overview(*, days: int = 30, country: str = "", language: str = "") -> dict[str, Any]:
    """Return aggregate usage, feedback, topic, locale, and daily trend data."""
    days = max(1, min(int(days), 365))
    since = datetime.now(UTC) - timedelta(days=days)
    filters = ["created_at >= :since"]
    parameters: dict[str, Any] = {"since": since}
    if country:
        filters.append("country = :country")
        parameters["country"] = country.upper()
    if language:
        filters.append("language = :language")
        parameters["language"] = language.lower()
    where = " AND ".join(filters)

    with get_engine().connect() as connection:
        totals = connection.execute(
            text(
                f"""
                SELECT COUNT(*) AS questions,
                       COUNT(DISTINCT session_id) AS users,
                       COALESCE(SUM(input_tokens + output_tokens), 0) AS tokens,
                       COALESCE(AVG(confidence), 0) AS confidence,
                       COUNT(*) FILTER (WHERE fallback) AS unanswered
                FROM chat_analytics WHERE {where}
                """
            ),
            parameters,
        ).mappings().one()
        feedback = connection.execute(
            text(
                f"""
                SELECT COUNT(*) FILTER (WHERE f.rating > 0) AS helpful,
                       COUNT(*) FILTER (WHERE f.rating < 0) AS not_helpful
                FROM feedback_events f
                LEFT JOIN chat_analytics c ON c.correlation_id = f.correlation_id
                WHERE COALESCE(c.created_at, f.created_at) >= :since
                  {"AND c.country = :country" if country else ""}
                  {"AND c.language = :language" if language else ""}
                """
            ),
            parameters,
        ).mappings().one()
        topics = connection.execute(
            text(f"SELECT topic AS label, COUNT(*) AS value FROM chat_analytics WHERE {where} GROUP BY topic ORDER BY value DESC LIMIT 8"),
            parameters,
        ).mappings().all()
        countries = connection.execute(
            text(f"SELECT country AS label, COUNT(*) AS value FROM chat_analytics WHERE {where} GROUP BY country ORDER BY value DESC"),
            parameters,
        ).mappings().all()
        languages = connection.execute(
            text(f"SELECT language AS label, COUNT(*) AS value FROM chat_analytics WHERE {where} GROUP BY language ORDER BY value DESC"),
            parameters,
        ).mappings().all()
        trend = connection.execute(
            text(
                f"""
                SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS date,
                       COUNT(*) AS questions,
                       COUNT(DISTINCT session_id) AS users,
                       COALESCE(SUM(input_tokens + output_tokens), 0) AS tokens
                FROM chat_analytics WHERE {where}
                GROUP BY date_trunc('day', created_at)
                ORDER BY date_trunc('day', created_at)
                """
            ),
            parameters,
        ).mappings().all()

    helpful = int(feedback["helpful"] or 0)
    not_helpful = int(feedback["not_helpful"] or 0)
    rated = helpful + not_helpful
    return {
        "rangeDays": days,
        "totals": {
            "questions": int(totals["questions"] or 0),
            "users": int(totals["users"] or 0),
            "tokens": int(totals["tokens"] or 0),
            "averageConfidence": round(float(totals["confidence"] or 0.0), 3),
            "unanswered": int(totals["unanswered"] or 0),
            "helpful": helpful,
            "notHelpful": not_helpful,
            "helpfulRate": round(helpful / rated, 3) if rated else 0.0,
        },
        "topics": [dict(row) for row in topics],
        "countries": [dict(row) for row in countries],
        "languages": [dict(row) for row in languages],
        "trend": [dict(row) for row in trend],
    }


def interaction_list(
    *,
    days: int = 30,
    country: str = "",
    language: str = "",
    feedback: str = "all",
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return recent questions with optional negative-feedback filtering."""
    since = datetime.now(UTC) - timedelta(days=max(1, min(int(days), 365)))
    filters = ["c.created_at >= :since"]
    parameters: dict[str, Any] = {"since": since, "limit": max(1, min(int(limit), 500))}
    if country:
        filters.append("c.country = :country")
        parameters["country"] = country.upper()
    if language:
        filters.append("c.language = :language")
        parameters["language"] = language.lower()
    if feedback == "not_helpful":
        filters.append("f.rating < 0")
    elif feedback == "helpful":
        filters.append("f.rating > 0")
    where = " AND ".join(filters)
    with get_engine().connect() as connection:
        rows = connection.execute(
            text(
                f"""
                SELECT c.correlation_id, c.session_id, c.country, c.language,
                       c.question, c.answer, c.topic, c.confidence, c.source_count,
                       c.input_tokens + c.output_tokens AS tokens, c.fallback,
                       c.failure_layer, c.created_at, f.rating, f.comment
                FROM chat_analytics c
                LEFT JOIN LATERAL (
                    SELECT rating, comment FROM feedback_events
                    WHERE correlation_id = c.correlation_id
                    ORDER BY created_at DESC LIMIT 1
                ) f ON true
                WHERE {where}
                ORDER BY c.created_at DESC LIMIT :limit
                """
            ),
            parameters,
        ).mappings().all()
    return [
        {
            **dict(row),
            "created_at": row["created_at"].isoformat() if row["created_at"] else "",
        }
        for row in rows
    ]
