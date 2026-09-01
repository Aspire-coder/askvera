from datetime import UTC, datetime

import pytest

from pydantic import ValidationError

from services.analytics import (
    _analytics_window,
    _live_session_scope,
    _model_routing_metadata,
    _normalize_traffic_source,
    _redacted_preview,
    _routing_cost_projection,
)
from app.response.models import ChatResponse
from utils.validators import ChatRequest


def test_analytics_window_preserves_explicit_utc_bounds() -> None:
    start = datetime(2026, 7, 22, 13, 0, tzinfo=UTC)
    end = datetime(2026, 7, 22, 15, 0, tzinfo=UTC)

    assert _analytics_window(days=30, start=start, end=end) == (start, end)


def test_analytics_window_converts_offset_times_to_utc() -> None:
    start = datetime.fromisoformat("2026-07-22T09:00:00-04:00")
    end = datetime.fromisoformat("2026-07-22T11:00:00-04:00")

    assert _analytics_window(days=30, start=start, end=end) == (
        datetime(2026, 7, 22, 13, 0, tzinfo=UTC),
        datetime(2026, 7, 22, 15, 0, tzinfo=UTC),
    )


def test_analytics_window_rejects_an_inverted_range() -> None:
    start = datetime(2026, 7, 22, 15, 0, tzinfo=UTC)
    end = datetime(2026, 7, 22, 13, 0, tzinfo=UTC)

    with pytest.raises(ValueError, match="start time must be before"):
        _analytics_window(days=30, start=start, end=end)


def test_traffic_source_defaults_to_widget() -> None:
    request = ChatRequest(
        message="How do I become a manager?",
        sessionId="session-1",
        country="US",
        language="en",
    )

    assert request.trafficSource == "widget"


def test_redacted_interaction_preview_scrubs_sensitive_values() -> None:
    preview = _redacted_preview("Contact me at person@example.com. Card 4111 1111 1111 1111")

    assert "person@example.com" not in preview
    assert "4111 1111 1111 1111" not in preview


def test_traffic_source_accepts_supported_test_categories() -> None:
    request = ChatRequest(
        message="How do I become a manager?",
        sessionId="session-1",
        country="US",
        language="en",
        trafficSource="EVALUATION",
    )

    assert request.trafficSource == "evaluation"
    assert _normalize_traffic_source("backend_test") == "backend_test"
    assert _normalize_traffic_source("legacy") == "legacy"


def test_traffic_source_rejects_unknown_categories() -> None:
    with pytest.raises(ValidationError, match="Unsupported traffic source"):
        ChatRequest(
            message="How do I become a manager?",
            sessionId="session-1",
            country="US",
            language="en",
            trafficSource="unknown",
        )

    with pytest.raises(ValueError, match="Unsupported traffic source"):
        _normalize_traffic_source("unknown")


def test_live_session_scope_excludes_ended_and_expired_sessions() -> None:
    where, parameters = _live_session_scope(country="", language="", traffic_source="")

    assert "s.ended_at IS NULL" in where
    assert "s.expires_at > now()" in where
    assert "s.consent_accepted = true" in where
    assert parameters == {}


def test_live_session_scope_applies_locale_and_traffic_filters() -> None:
    where, parameters = _live_session_scope(country="us", language="EN", traffic_source="widget")

    assert "consent_log" in where
    assert "chat_analytics" in where
    assert parameters == {"country": "US", "language": "en", "traffic_source": "widget"}


def test_model_routing_metadata_preserves_shadow_decision() -> None:
    response = ChatResponse(
        answer="Answer",
        citations=[],
        suggestions=[],
        cards=[],
        confidence=0.9,
        metadata={
            "provider": "claude",
            "model_route_mode": "shadow",
            "model_route_target": "fast",
            "model_route_reasons": ["low_risk_evidence"],
            "model_route_actual_model": "sonnet-production",
            "latency_ms": 1250,
        },
        correlation_id="route-1",
    )

    metadata = _model_routing_metadata(response)

    assert metadata["model_route_mode"] == "shadow"
    assert metadata["model_route_target"] == "fast"
    assert metadata["model_route_reasons"] == '["low_risk_evidence"]'
    assert metadata["actual_model"] == "sonnet-production"
    assert metadata["generation_latency_ms"] == 1250
    assert metadata["cache_hit"] is False


def test_model_routing_metadata_marks_cache_without_inventing_a_route() -> None:
    response = ChatResponse(
        answer="Cached answer",
        citations=[],
        suggestions=[],
        cards=[],
        confidence=0.9,
        metadata={"provider": "cache", "cache": "semantic", "model_name": "cached response"},
        correlation_id="route-2",
    )

    metadata = _model_routing_metadata(response)

    assert metadata["cache_hit"] is True
    assert metadata["model_route_target"] == ""
    assert metadata["actual_model"] == ""


def test_routing_cost_projection_compares_against_current_primary(monkeypatch) -> None:
    monkeypatch.setattr("services.analytics.settings.MODEL_ROUTING_FAST_INPUT_USD_PER_MILLION", 1.0)
    monkeypatch.setattr("services.analytics.settings.MODEL_ROUTING_FAST_OUTPUT_USD_PER_MILLION", 5.0)
    monkeypatch.setattr("services.analytics.settings.MODEL_ROUTING_COMPLEX_INPUT_USD_PER_MILLION", 3.0)
    monkeypatch.setattr("services.analytics.settings.MODEL_ROUTING_COMPLEX_OUTPUT_USD_PER_MILLION", 15.0)
    monkeypatch.setattr("services.analytics.settings.BEDROCK_MODEL_ARN", "global.claude-haiku-4-5")
    targets = [
        {"target": "fast", "input_tokens": 1_000_000, "output_tokens": 100_000},
        {"target": "complex", "input_tokens": 1_000_000, "output_tokens": 100_000},
    ]

    result = _routing_cost_projection(targets)

    assert result["baselineUsd"] == 3.0
    assert result["currentUsd"] == 3.0
    assert result["projectedUsd"] == 6.0
    assert result["projectedDeltaUsd"] == 3.0
    assert result["projectedSavingsUsd"] == 0.0
