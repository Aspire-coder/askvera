from datetime import UTC, datetime

import pytest

from pydantic import ValidationError

from services.analytics import _analytics_window, _normalize_traffic_source
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
