"""Run one bounded batch of scheduled aggregate analytics reports."""

from services.analytics_notifications import process_due_analytics_reports


if __name__ == "__main__":
    print(process_due_analytics_reports())
