"""Validation tests for the Insights review and reporting workflow."""

import pytest

from config import settings
from services import analytics_governance, analytics_notifications


def test_saved_view_rejects_invalid_schedule_before_database_access() -> None:
    with pytest.raises(ValueError, match="schedule"):
        analytics_governance.save_view(
            view_id=None,
            name="Review",
            owner_sub="admin",
            filters={},
            schedule="hourly",
            report_email="owner@example.com",
            alert_not_helpful_threshold=None,
        )


def test_saved_view_rejects_invalid_alert_threshold_before_database_access() -> None:
    with pytest.raises(ValueError, match="threshold"):
        analytics_governance.save_view(
            view_id=None,
            name="Review",
            owner_sub="admin",
            filters={},
            schedule="none",
            report_email="",
            alert_not_helpful_threshold=1.1,
        )


def test_scheduled_reports_are_safe_by_default(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ANALYTICS_REPORTS_ENABLED", False)

    assert analytics_notifications.process_due_analytics_reports() == {
        "processed": 0,
        "sent": 0,
        "failed": 0,
    }
