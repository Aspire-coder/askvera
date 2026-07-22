from datetime import UTC, datetime

import pytest

from services.analytics import _analytics_window


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
