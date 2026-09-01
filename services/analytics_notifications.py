"""Send due aggregate Insights reports and quality-threshold alerts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import text

from config import settings
from services.analytics import analytics_overview
from services.aws_clients import get_aws_clients
from services.db import get_engine


def _next_run(schedule: str) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=1 if schedule == "daily" else 7)


def _report_text(name: str, overview: dict[str, Any], *, alert: bool) -> str:
    totals = overview["totals"]
    rated = int(totals["helpful"]) + int(totals["notHelpful"])
    not_helpful_rate = int(totals["notHelpful"]) / rated if rated else 0
    heading = "Quality alert" if alert else "Scheduled Insights report"
    return (
        f"{heading}: {name}\n\n"
        f"Questions: {totals['questions']}\n"
        f"Unique sessions: {totals['users']}\n"
        f"Helpful rate: {float(totals['helpfulRate']) * 100:.1f}%\n"
        f"Not-helpful rate: {not_helpful_rate * 100:.1f}%\n"
        f"Average confidence: {float(totals['averageConfidence']) * 100:.1f}%\n"
        f"Unanswered: {totals['unanswered']}\n\n"
        "This report contains aggregate operational data only. Open the AskVera Operations portal to investigate individual answers."
    )


def process_due_analytics_reports(limit: int = 25) -> dict[str, int]:
    """Process a bounded batch; intended for a systemd timer or scheduled job."""
    if not settings.ANALYTICS_REPORTS_ENABLED or not settings.ANALYTICS_REPORT_FROM:
        return {"processed": 0, "sent": 0, "failed": 0}
    with get_engine().connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT * FROM analytics_saved_views
                WHERE enabled = true AND schedule <> 'none'
                  AND next_run_at IS NOT NULL AND next_run_at <= now()
                ORDER BY next_run_at LIMIT :limit
                """
            ),
            {"limit": max(1, min(limit, 100))},
        ).mappings().all()
    sent = 0
    failed = 0
    for row in rows:
        filters = dict(row.get("filters") or {})
        allowed = {item for item in str(filters.get("_allowed_countries") or "").split(",") if item}
        try:
            overview = analytics_overview(
                days=int(filters.get("days") or 30),
                country=str(filters.get("country") or ""),
                language=str(filters.get("language") or ""),
                traffic_source=str(filters.get("trafficSource") or ""),
                allowed_countries=allowed or set(),
            )
            totals = overview["totals"]
            rated = int(totals["helpful"]) + int(totals["notHelpful"])
            rate = int(totals["notHelpful"]) / rated if rated else 0
            threshold = row.get("alert_not_helpful_threshold")
            alert = threshold is not None and rate >= float(threshold)
            recipient = str(row.get("report_email") or "").strip()
            if not recipient:
                raise ValueError("Report recipient is missing.")
            get_aws_clients().ses.send_email(
                Source=settings.ANALYTICS_REPORT_FROM,
                Destination={"ToAddresses": [recipient]},
                Message={
                    "Subject": {"Data": f"AskVera {'quality alert' if alert else 'Insights report'} - {row['name']}", "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": _report_text(str(row["name"]), overview, alert=alert), "Charset": "UTF-8"}},
                },
            )
            with get_engine().begin() as connection:
                connection.execute(
                    text("UPDATE analytics_saved_views SET last_sent_at = now(), next_run_at = :next_run, updated_at = now() WHERE id = :id"),
                    {"id": row["id"], "next_run": _next_run(str(row["schedule"]))},
                )
            sent += 1
        except (ValueError, BotoCoreError, ClientError):
            failed += 1
    return {"processed": len(rows), "sent": sent, "failed": failed}
