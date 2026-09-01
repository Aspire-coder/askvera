"""Operational analytics persistence and queries for AskVera administrators."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any
from xml.sax.saxutils import escape

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.response.models import ChatResponse
from config import settings
from services.db import get_engine
from utils.redaction import redact_common_pii
from utils.logging import get_logger
from utils.validators import TRAFFIC_SOURCES, ChatRequest, FeedbackRequest, SupportRequest

LOGGER = get_logger("services.analytics")
FILTER_TRAFFIC_SOURCES = TRAFFIC_SOURCES | {"legacy"}
REDACTED_INTERACTION_PREVIEW_LIMIT = 800
MAX_INTERACTION_EXPORT_ROWS = 5000
INTERACTION_EXPORT_COLUMNS = [
    "created_at", "correlation_id", "session_id", "country", "language",
    "traffic_source", "question", "answer", "topic", "confidence",
    "source_count", "tokens", "fallback", "failure_layer", "rating",
    "comment", "expected_answer",
]


def _redacted_preview(value: Any, *, limit: int = REDACTED_INTERACTION_PREVIEW_LIMIT) -> str:
    """Return a compact PII-scrubbed preview suitable for operational review."""
    return redact_common_pii(" ".join(str(value or "").split()))[:limit]


def _normalize_traffic_source(value: str) -> str:
    normalized = value.lower().strip()
    if normalized and normalized not in FILTER_TRAFFIC_SOURCES:
        raise ValueError("Unsupported traffic source.")
    return normalized


def _analytics_window(
    *,
    days: int,
    start: datetime | None = None,
    end: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Return a bounded UTC analytics window, preferring explicit timestamps."""
    now = datetime.now(UTC)

    def as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    window_start = as_utc(start) if start else now - timedelta(days=max(1, min(int(days), 365)))
    window_end = as_utc(end) if end else now
    if window_start >= window_end:
        raise ValueError("The analytics start time must be before the end time.")
    return window_start, window_end


def _market_scope(
    *,
    column: str,
    country: str,
    allowed_countries: set[str] | None,
    parameters: dict[str, Any],
) -> str:
    """Build a concrete country predicate without interpolating user input."""
    if country:
        parameters["country"] = country.upper()
        return f"{column} = :country"
    if allowed_countries is None:
        return ""
    normalized = sorted(value.upper() for value in allowed_countries)
    if not normalized:
        return "1 = 0"
    placeholders: list[str] = []
    for index, value in enumerate(normalized):
        key = f"scope_country_{index}"
        parameters[key] = value
        placeholders.append(f":{key}")
    return f"{column} IN ({', '.join(placeholders)})"


def _live_session_scope(
    *,
    country: str,
    language: str,
    traffic_source: str,
    allowed_countries: set[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build the lifecycle query scope independently of the reporting date range."""
    filters = [
        "s.ended_at IS NULL",
        "s.expires_at > now()",
        "s.consent_accepted = true",
    ]
    parameters: dict[str, Any] = {}
    market_filter = _market_scope(
        column="cl.country",
        country=country,
        allowed_countries=allowed_countries,
        parameters=parameters,
    )
    if market_filter or language:
        consent_filters = ["cl.session_id = s.session_id", "cl.accepted = true"]
        if market_filter:
            consent_filters.append(market_filter)
        if language:
            consent_filters.append("cl.lang = :language")
            parameters["language"] = language.lower()
        filters.append(f"EXISTS (SELECT 1 FROM consent_log cl WHERE {' AND '.join(consent_filters)})")
    if traffic_source:
        filters.append(
            "EXISTS (SELECT 1 FROM chat_analytics ca "
            "WHERE ca.session_id = s.session_id AND ca.traffic_source = :traffic_source)"
        )
        parameters["traffic_source"] = traffic_source
    return " AND ".join(filters), parameters


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


def _model_routing_metadata(response: ChatResponse) -> dict[str, Any]:
    """Normalize privacy-safe routing telemetry before database persistence."""
    metadata = response.metadata if isinstance(response.metadata, dict) else {}
    provider = str(metadata.get("provider") or "").strip().lower()
    cache_state = str(metadata.get("cache") or "").strip().lower()
    cache_hit = provider == "cache" or cache_state in {"hit", "exact", "semantic"}
    reasons = metadata.get("model_route_reasons")
    if not isinstance(reasons, (list, tuple)):
        reasons = []
    normalized_reasons = [str(reason)[:80] for reason in reasons if str(reason).strip()][:12]
    try:
        latency_ms = max(0, int(metadata.get("latency_ms") or 0))
    except (TypeError, ValueError):
        latency_ms = 0
    actual_model = "" if cache_hit else str(
        metadata.get("model_route_actual_model") or metadata.get("model_name") or ""
    )[:500]
    return {
        "model_route_mode": str(metadata.get("model_route_mode") or "")[:24],
        "model_route_target": str(metadata.get("model_route_target") or "")[:24],
        "model_route_reasons": json.dumps(normalized_reasons),
        "actual_model": actual_model,
        "generation_latency_ms": latency_ms,
        "cache_hit": cache_hit,
    }


def record_chat_interaction(body: ChatRequest, response: ChatResponse, correlation_id: str) -> None:
    """Persist a scrubbed chat outcome for aggregate analytics and QA review."""
    input_tokens, output_tokens = _token_counts(response)
    routing = _model_routing_metadata(response)
    try:
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO chat_analytics (
                        correlation_id, session_id, country, language, question,
                        answer, topic, confidence, source_count, input_tokens,
                        output_tokens, fallback, failure_layer, traffic_source,
                        model_route_mode, model_route_target, model_route_reasons,
                        actual_model, generation_latency_ms, cache_hit, created_at
                    ) VALUES (
                        :correlation_id, :session_id, :country, :language, :question,
                        :answer, :topic, :confidence, :source_count, :input_tokens,
                        :output_tokens, :fallback, :failure_layer, :traffic_source,
                        :model_route_mode, :model_route_target,
                        CAST(:model_route_reasons AS JSONB), :actual_model,
                        :generation_latency_ms, :cache_hit, now()
                    )
                    ON CONFLICT (correlation_id) DO UPDATE SET
                        answer = EXCLUDED.answer,
                        confidence = EXCLUDED.confidence,
                        source_count = EXCLUDED.source_count,
                        input_tokens = EXCLUDED.input_tokens,
                        output_tokens = EXCLUDED.output_tokens,
                        traffic_source = EXCLUDED.traffic_source,
                        fallback = EXCLUDED.fallback,
                        failure_layer = EXCLUDED.failure_layer,
                        model_route_mode = EXCLUDED.model_route_mode,
                        model_route_target = EXCLUDED.model_route_target,
                        model_route_reasons = EXCLUDED.model_route_reasons,
                        actual_model = EXCLUDED.actual_model,
                        generation_latency_ms = EXCLUDED.generation_latency_ms,
                        cache_hit = EXCLUDED.cache_hit
                    """
                ),
                {
                    "correlation_id": correlation_id,
                    "session_id": body.sessionId,
                    "country": body.country,
                    "language": body.language,
                    "question": redact_common_pii(" ".join(body.message.split()))[:4000],
                    "answer": redact_common_pii(response.answer)[:12_000],
                    "topic": _topic(response),
                    "confidence": float(response.confidence or 0.0),
                    "source_count": len(response.citations),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "fallback": bool(response.metadata.get("fallback")),
                    "failure_layer": str(response.metadata.get("failure_layer") or ""),
                    "traffic_source": body.trafficSource,
                    **routing,
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
                        comment, expected_answer, expected_answer_present,
                        request_type, country, language, created_at
                    ) VALUES (
                        :event_id, :correlation_id, :session_id, :message_id, :rating,
                        :comment, :expected_answer, :expected_answer_present,
                        :request_type, :country, :language, now()
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
                    "comment": redact_common_pii(feedback.comment or "")[:4000],
                    "expected_answer": redact_common_pii(feedback.expected_answer or "")[:12_000],
                    "expected_answer_present": bool(feedback.expected_answer),
                    "request_type": feedback.requestType,
                    "country": str(metadata.get("country") or ""),
                    "language": str(metadata.get("language") or ""),
                },
            )
    except SQLAlchemyError:
        LOGGER.exception("feedback_analytics_write_failed", correlation_id=correlation_id)


def record_support_delivery(
    request: SupportRequest,
    *,
    ticket_id: str,
    correlation_id: str,
    route_name: str,
) -> None:
    """Store delivery metadata without retaining support contact details or text."""
    try:
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO support_requests (
                        ticket_id, correlation_id, session_id, message_id, country,
                        language, route_name, delivery_status, created_at
                    ) VALUES (
                        :ticket_id, :correlation_id, :session_id, :message_id, :country,
                        :language, :route_name, 'submitted', now()
                    )
                    ON CONFLICT (ticket_id) DO NOTHING
                    """
                ),
                {
                    "ticket_id": ticket_id,
                    "correlation_id": correlation_id,
                    "session_id": request.sessionId,
                    "message_id": request.messageId,
                    "country": request.country,
                    "language": request.language,
                    "route_name": route_name,
                },
            )
    except SQLAlchemyError:
        LOGGER.exception("support_audit_write_failed", correlation_id=correlation_id, ticket_id=ticket_id)


def analytics_overview(
    *,
    days: int = 30,
    country: str = "",
    language: str = "",
    traffic_source: str = "",
    allowed_countries: set[str] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    """Return aggregate usage, feedback, topic, locale, and daily trend data."""
    days = max(1, min(int(days), 365))
    since, until = _analytics_window(days=days, start=start, end=end)
    filters = ["created_at >= :since", "created_at < :until"]
    parameters: dict[str, Any] = {"since": since, "until": until}
    traffic_source = _normalize_traffic_source(traffic_source)
    market_filter = _market_scope(
        column="country",
        country=country,
        allowed_countries=allowed_countries,
        parameters=parameters,
    )
    if market_filter:
        filters.append(market_filter)
    if language:
        filters.append("language = :language")
        parameters["language"] = language.lower()
    if traffic_source:
        filters.append("traffic_source = :traffic_source")
        parameters["traffic_source"] = traffic_source
    where = " AND ".join(filters)

    with get_engine().connect() as connection:
        totals = connection.execute(
            text(
                f"""
                SELECT COUNT(*) AS questions,
                       COUNT(DISTINCT session_id) AS users,
                       COALESCE(SUM(input_tokens), 0) AS input_tokens,
                       COALESCE(SUM(output_tokens), 0) AS output_tokens,
                       COALESCE(SUM(input_tokens + output_tokens), 0) AS tokens,
                       COALESCE(AVG(confidence), 0) AS confidence,
                       COUNT(*) FILTER (WHERE fallback) AS unanswered
                FROM chat_analytics WHERE {where}
                """
            ),
            parameters,
        ).mappings().one()
        live_session_scope, live_parameters = _live_session_scope(
            country=country,
            language=language,
            traffic_source=traffic_source,
            allowed_countries=allowed_countries,
        )
        feedback_market_filter = _market_scope(
            column="c.country",
            country=country,
            allowed_countries=allowed_countries,
            parameters=parameters,
        )
        live_sessions = connection.execute(
            text("SELECT COUNT(*) FROM chat_sessions s WHERE " + live_session_scope),
            live_parameters,
        ).scalar_one()
        feedback = connection.execute(
            text(
                f"""
                SELECT COUNT(*) FILTER (WHERE f.rating > 0) AS helpful,
                       COUNT(*) FILTER (WHERE f.rating < 0) AS not_helpful
                FROM feedback_events f
                LEFT JOIN chat_analytics c ON c.correlation_id = f.correlation_id
                WHERE COALESCE(c.created_at, f.created_at) >= :since
                  AND COALESCE(c.created_at, f.created_at) < :until
                  {f"AND {feedback_market_filter}" if feedback_market_filter else ""}
                  {"AND c.language = :language" if language else ""}
                  {"AND c.traffic_source = :traffic_source" if traffic_source else ""}
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
            "liveSessions": int(live_sessions or 0),
            "inputTokens": int(totals["input_tokens"] or 0),
            "outputTokens": int(totals["output_tokens"] or 0),
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


def _routing_cost_projection(targets: list[dict[str, Any]]) -> dict[str, float | str]:
    """Compare proposed routing with the model that currently serves production."""
    fast_input = float(settings.MODEL_ROUTING_FAST_INPUT_USD_PER_MILLION)
    fast_output = float(settings.MODEL_ROUTING_FAST_OUTPUT_USD_PER_MILLION)
    complex_input = float(settings.MODEL_ROUTING_COMPLEX_INPUT_USD_PER_MILLION)
    complex_output = float(settings.MODEL_ROUTING_COMPLEX_OUTPUT_USD_PER_MILLION)
    total_input = sum(int(row.get("input_tokens") or 0) for row in targets)
    total_output = sum(int(row.get("output_tokens") or 0) for row in targets)
    primary_model = str(settings.BEDROCK_MODEL_ARN or "").lower()
    current_is_fast = "haiku" in primary_model
    current_input_rate = fast_input if current_is_fast else complex_input
    current_output_rate = fast_output if current_is_fast else complex_output
    current = (
        total_input * current_input_rate + total_output * current_output_rate
    ) / 1_000_000
    projected = 0.0
    for row in targets:
        is_fast = str(row.get("target") or "") == "fast"
        input_rate = fast_input if is_fast else complex_input
        output_rate = fast_output if is_fast else complex_output
        projected += (
            int(row.get("input_tokens") or 0) * input_rate
            + int(row.get("output_tokens") or 0) * output_rate
        ) / 1_000_000
    delta = projected - current
    savings = max(0.0, -delta)
    return {
        "baselineUsd": round(current, 4),
        "currentUsd": round(current, 4),
        "projectedUsd": round(projected, 4),
        "projectedDeltaUsd": round(delta, 4),
        "projectedSavingsUsd": round(savings, 4),
        "savingsRate": round(savings / current, 4) if current else 0.0,
        "pricingLabel": str(settings.MODEL_ROUTING_PRICING_LABEL),
    }


def model_routing_report(
    *,
    days: int = 7,
    country: str = "",
    allowed_countries: set[str] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    """Return durable, RBAC-scoped model-routing telemetry for Operations."""
    days = max(1, min(int(days), 365))
    since, until = _analytics_window(days=days, start=start, end=end)
    filters = ["created_at >= :since", "created_at < :until"]
    parameters: dict[str, Any] = {"since": since, "until": until}
    market_filter = _market_scope(
        column="country",
        country=country,
        allowed_countries=allowed_countries,
        parameters=parameters,
    )
    if market_filter:
        filters.append(market_filter)
    where = " AND ".join(filters)

    with get_engine().connect() as connection:
        totals_row = connection.execute(
            text(
                f"""
                SELECT COUNT(*) AS questions,
                       COUNT(*) FILTER (WHERE cache_hit) AS cached,
                       COUNT(*) FILTER (
                           WHERE model_route_target IN ('fast', 'complex')
                       ) AS evaluated,
                       COUNT(*) FILTER (WHERE model_route_target = 'fast') AS proposed_fast,
                       COUNT(*) FILTER (WHERE model_route_target = 'complex') AS proposed_complex,
                       COALESCE(AVG(generation_latency_ms) FILTER (
                           WHERE generation_latency_ms > 0
                       ), 0) AS average_generation_latency_ms
                FROM chat_analytics WHERE {where}
                """
            ),
            parameters,
        ).mappings().one()
        targets = connection.execute(
            text(
                f"""
                SELECT model_route_target AS target,
                       COUNT(*) AS questions,
                       COALESCE(SUM(input_tokens), 0) AS input_tokens,
                       COALESCE(SUM(output_tokens), 0) AS output_tokens,
                       COALESCE(AVG(generation_latency_ms) FILTER (
                           WHERE generation_latency_ms > 0
                       ), 0) AS average_latency_ms
                FROM chat_analytics
                WHERE {where} AND model_route_target IN ('fast', 'complex')
                GROUP BY model_route_target ORDER BY model_route_target
                """
            ),
            parameters,
        ).mappings().all()
        actual_models = connection.execute(
            text(
                f"""
                SELECT actual_model AS label, COUNT(*) AS value
                FROM chat_analytics
                WHERE {where} AND actual_model <> ''
                GROUP BY actual_model ORDER BY value DESC LIMIT 5
                """
            ),
            parameters,
        ).mappings().all()
        reasons = connection.execute(
            text(
                f"""
                SELECT reason AS label, COUNT(*) AS value
                FROM chat_analytics,
                     LATERAL jsonb_array_elements_text(model_route_reasons)
                         AS route_reason(reason)
                WHERE {where}
                GROUP BY reason ORDER BY value DESC LIMIT 6
                """
            ),
            parameters,
        ).mappings().all()
        countries = connection.execute(
            text(
                f"""
                SELECT country AS label,
                       COUNT(*) FILTER (
                           WHERE model_route_target IN ('fast', 'complex')
                       ) AS evaluated,
                       COUNT(*) FILTER (WHERE model_route_target = 'fast') AS fast,
                       COUNT(*) FILTER (WHERE model_route_target = 'complex') AS complex
                FROM chat_analytics WHERE {where}
                GROUP BY country ORDER BY evaluated DESC
                """
            ),
            parameters,
        ).mappings().all()
        trend = connection.execute(
            text(
                f"""
                SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS date,
                       COUNT(*) FILTER (WHERE model_route_target = 'fast') AS fast,
                       COUNT(*) FILTER (WHERE model_route_target = 'complex') AS complex,
                       COUNT(*) FILTER (WHERE cache_hit) AS cached
                FROM chat_analytics WHERE {where}
                GROUP BY date_trunc('day', created_at)
                ORDER BY date_trunc('day', created_at)
                """
            ),
            parameters,
        ).mappings().all()

    questions = int(totals_row["questions"] or 0)
    evaluated = int(totals_row["evaluated"] or 0)
    cached = int(totals_row["cached"] or 0)
    proposed_fast = int(totals_row["proposed_fast"] or 0)
    proposed_complex = int(totals_row["proposed_complex"] or 0)
    target_rows = [dict(row) for row in targets]
    return {
        "rangeDays": days,
        "mode": str(settings.MODEL_ROUTING_MODE),
        "models": {
            "primary": str(settings.BEDROCK_MODEL_ARN),
            "fast": str(settings.BEDROCK_FAST_MODEL_ID),
            "complex": str(settings.BEDROCK_COMPLEX_MODEL_ID),
        },
        "totals": {
            "questions": questions,
            "evaluated": evaluated,
            "cached": cached,
            "unclassified": max(0, questions - cached - evaluated),
            "proposedFast": proposed_fast,
            "proposedComplex": proposed_complex,
            "fastShare": round(proposed_fast / evaluated, 4) if evaluated else 0.0,
            "averageGenerationLatencyMs": round(
                float(totals_row["average_generation_latency_ms"] or 0.0), 1
            ),
        },
        "cost": _routing_cost_projection(target_rows),
        "targets": target_rows,
        "actualModels": [dict(row) for row in actual_models],
        "reasons": [dict(row) for row in reasons],
        "countries": [dict(row) for row in countries],
        "trend": [dict(row) for row in trend],
    }


def interaction_list(
    *,
    days: int = 30,
    country: str = "",
    language: str = "",
    traffic_source: str = "",
    allowed_countries: set[str] | None = None,
    feedback: str = "all",
    search: str = "",
    sort: str = "newest",
    limit: int = 100,
    page: int = 1,
    page_size: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    redact_content: bool = False,
) -> list[dict[str, Any]]:
    """Return recent questions with optional filtering."""
    result = interaction_page(
        days=days,
        country=country,
        language=language,
        traffic_source=traffic_source,
        allowed_countries=allowed_countries,
        feedback=feedback,
        search=search,
        sort=sort,
        limit=limit,
        page=page,
        page_size=page_size,
        start=start,
        end=end,
        redact_content=redact_content,
    )
    return result["items"]


def interaction_page(
    *,
    days: int = 30,
    country: str = "",
    language: str = "",
    traffic_source: str = "",
    allowed_countries: set[str] | None = None,
    feedback: str = "all",
    search: str = "",
    sort: str = "newest",
    page: int = 1,
    page_size: int = 50,
    limit: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    redact_content: bool = False,
) -> dict[str, Any]:
    """Return a server-filtered, server-paginated interaction page."""
    since, until = _analytics_window(days=days, start=start, end=end)
    filters = ["c.created_at >= :since", "c.created_at < :until"]
    safe_page = max(1, int(page))
    max_page_size = MAX_INTERACTION_EXPORT_ROWS if limit is not None else 100
    safe_page_size = max(1, min(int(page_size or limit or 50), max_page_size))
    parameters: dict[str, Any] = {
        "since": since,
        "until": until,
        "limit": safe_page_size,
        "offset": (safe_page - 1) * safe_page_size,
    }
    traffic_source = _normalize_traffic_source(traffic_source)
    market_filter = _market_scope(
        column="c.country",
        country=country,
        allowed_countries=allowed_countries,
        parameters=parameters,
    )
    if market_filter:
        filters.append(market_filter)
    if language:
        filters.append("c.language = :language")
        parameters["language"] = language.lower()
    if traffic_source:
        filters.append("c.traffic_source = :traffic_source")
        parameters["traffic_source"] = traffic_source
    if feedback == "not_helpful":
        filters.append("f.rating < 0")
    elif feedback == "helpful":
        filters.append("f.rating > 0")
    elif feedback == "unrated":
        filters.append("f.rating IS NULL")
    if search.strip():
        filters.append("(LOWER(c.question) LIKE :search OR LOWER(c.topic) LIKE :search)")
        parameters["search"] = f"%{search.strip().lower()}%"
    sort_sql = {
        "newest": "c.created_at DESC",
        "oldest": "c.created_at ASC",
        "lowest_confidence": "c.confidence ASC",
        "highest_confidence": "c.confidence DESC",
        "helpful_first": "CASE WHEN f.rating > 0 THEN 0 ELSE 1 END ASC, c.created_at DESC",
        "not_helpful_first": "CASE WHEN f.rating < 0 THEN 0 ELSE 1 END ASC, c.created_at DESC",
    }.get(sort)
    if sort_sql is None:
        raise ValueError("Unsupported interaction sort.")
    where = " AND ".join(filters)
    with get_engine().connect() as connection:
        total = int(connection.execute(
            text(
                f"""
                SELECT COUNT(*)
                FROM chat_analytics c
                LEFT JOIN LATERAL (
                    SELECT rating FROM feedback_events
                    WHERE correlation_id = c.correlation_id
                    ORDER BY created_at DESC LIMIT 1
                ) f ON true
                WHERE {where}
                """
            ),
            parameters,
        ).scalar() or 0)
        rows = connection.execute(
            text(
                f"""
                SELECT c.correlation_id, c.session_id, c.country, c.language,
                       c.question, c.answer, c.topic, c.confidence, c.source_count,
                       c.input_tokens + c.output_tokens AS tokens, c.fallback,
                       c.failure_layer, c.traffic_source, c.created_at, f.rating, f.comment,
                       f.expected_answer, f.expected_answer_present,
                       rc.status AS review_status, rc.assignee_email,
                       rc.resolution_notes, rc.updated_at AS review_updated_at
                FROM chat_analytics c
                LEFT JOIN LATERAL (
                    SELECT rating, comment, expected_answer, expected_answer_present
                    FROM feedback_events
                    WHERE correlation_id = c.correlation_id
                    ORDER BY created_at DESC LIMIT 1
                ) f ON true
                LEFT JOIN answer_review_cases rc ON rc.correlation_id = c.correlation_id
                WHERE {where}
                ORDER BY {sort_sql}, c.correlation_id
                LIMIT :limit OFFSET :offset
                """
            ),
            parameters,
        ).mappings().all()
    interactions: list[dict[str, Any]] = []
    for row in rows:
        item = {
            **dict(row),
            "created_at": row["created_at"].isoformat() if row["created_at"] else "",
            "contentRedacted": redact_content,
        }
        item["review_updated_at"] = (
            item["review_updated_at"].isoformat() if item.get("review_updated_at") else None
        )
        if redact_content:
            for field in ("question", "answer", "comment", "expected_answer"):
                item[field] = _redacted_preview(item.get(field))
        interactions.append(item)
    return {
        "items": interactions,
        "total": total,
        "page": safe_page,
        "pageSize": safe_page_size,
        "totalPages": max(1, (total + safe_page_size - 1) // safe_page_size),
    }


def interaction_export_csv(**filters: Any) -> str:
    """Build a spreadsheet-friendly export using the same scoped interaction query."""
    rows = interaction_list(**filters)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=INTERACTION_EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _xlsx_column_name(number: int) -> str:
    """Return the Excel column name for a one-based column number."""
    name = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _xlsx_cell(reference: str, value: Any) -> str:
    """Write every export value as an escaped inline string to avoid formula injection."""
    raw_value = str(value if value is not None else "")
    safe_value = "".join(
        character for character in raw_value
        if character in "\t\n\r" or ord(character) >= 0x20
    )
    text_value = escape(safe_value)
    return f'<c r="{reference}" t="inlineStr"><is><t xml:space="preserve">{text_value}</t></is></c>'


def interaction_export_xlsx(**filters: Any) -> bytes:
    """Build a native Excel workbook from the same scoped interaction query as CSV."""
    rows = interaction_list(**filters)
    worksheet_rows = [INTERACTION_EXPORT_COLUMNS, *(
        [row.get(column, "") for column in INTERACTION_EXPORT_COLUMNS] for row in rows
    )]
    xml_rows: list[str] = []
    for row_number, row in enumerate(worksheet_rows, start=1):
        cells = "".join(
            _xlsx_cell(f"{_xlsx_column_name(column_number)}{row_number}", value)
            for column_number, value in enumerate(row, start=1)
        )
        xml_rows.append(f'<row r="{row_number}">{cells}</row>')

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Feedback" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    relationships_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )
    root_relationships_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )
    worksheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData></worksheet>'
    )

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", content_types_xml)
        workbook.writestr("_rels/.rels", root_relationships_xml)
        workbook.writestr("xl/workbook.xml", workbook_xml)
        workbook.writestr("xl/_rels/workbook.xml.rels", relationships_xml)
        workbook.writestr("xl/worksheets/sheet1.xml", worksheet_xml)
    return output.getvalue()
