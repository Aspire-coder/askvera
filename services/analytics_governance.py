"""Persistent review workflow and saved analytics views."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from services.db import get_engine


VALID_CASE_STATUSES = {"open", "investigating", "resolved"}
VALID_SCHEDULES = {"none", "daily", "weekly"}


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def review_case_market(correlation_id: str) -> str:
    """Return the market used for authorization before a review mutation."""
    with get_engine().connect() as connection:
        country = connection.execute(
            text("SELECT country FROM chat_analytics WHERE correlation_id = :correlation_id"),
            {"correlation_id": correlation_id},
        ).scalar()
    if not country:
        raise LookupError("Interaction not found.")
    return str(country).upper()


def update_review_case(
    correlation_id: str,
    *,
    status: str,
    assignee_email: str,
    resolution_notes: str,
    actor: str,
) -> dict[str, Any]:
    """Assign and move an answer review through its investigation lifecycle."""
    if status not in VALID_CASE_STATUSES:
        raise ValueError("Unsupported review status.")
    if len(resolution_notes.strip()) > 4000:
        raise ValueError("Resolution notes must be 4,000 characters or fewer.")
    resolved_at = datetime.now(timezone.utc) if status == "resolved" else None
    with get_engine().begin() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM chat_analytics WHERE correlation_id = :correlation_id"),
            {"correlation_id": correlation_id},
        ).scalar()
        if not exists:
            raise LookupError("Interaction not found.")
        row = connection.execute(
            text(
                """
                INSERT INTO answer_review_cases (
                    correlation_id, status, assignee_email, resolution_notes,
                    updated_by, resolved_at
                ) VALUES (
                    :correlation_id, :status, :assignee_email, :resolution_notes,
                    :actor, :resolved_at
                )
                ON CONFLICT (correlation_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    assignee_email = EXCLUDED.assignee_email,
                    resolution_notes = EXCLUDED.resolution_notes,
                    updated_by = EXCLUDED.updated_by,
                    resolved_at = EXCLUDED.resolved_at,
                    updated_at = now()
                RETURNING *
                """
            ),
            {
                "correlation_id": correlation_id,
                "status": status,
                "assignee_email": assignee_email.strip().lower(),
                "resolution_notes": resolution_notes.strip(),
                "actor": actor,
                "resolved_at": resolved_at,
            },
        ).mappings().one()
    result = dict(row)
    for field in ("created_at", "updated_at", "resolved_at"):
        result[field] = _iso(result.get(field))
    return result


def _next_run(schedule: str) -> datetime | None:
    now = datetime.now(timezone.utc)
    return now + timedelta(days=1 if schedule == "daily" else 7) if schedule != "none" else None


def list_saved_views(owner_sub: str, *, include_all: bool = False) -> list[dict[str, Any]]:
    """List the caller's saved views, or all views for super administrators."""
    where = "" if include_all else "WHERE owner_sub = :owner_sub"
    with get_engine().connect() as connection:
        rows = connection.execute(
            text(f"SELECT * FROM analytics_saved_views {where} ORDER BY name"),
            {"owner_sub": owner_sub},
        ).mappings().all()
    results = []
    for row in rows:
        item = dict(row)
        for field in ("last_sent_at", "next_run_at", "created_at", "updated_at"):
            item[field] = _iso(item.get(field))
        results.append(item)
    return results


def save_view(
    *,
    view_id: str | None,
    name: str,
    owner_sub: str,
    filters: dict[str, Any],
    schedule: str,
    report_email: str,
    alert_not_helpful_threshold: float | None,
) -> dict[str, Any]:
    """Create or update an analytics view and its notification schedule."""
    if not name.strip() or len(name.strip()) > 100:
        raise ValueError("A saved view name of 1 to 100 characters is required.")
    if schedule not in VALID_SCHEDULES:
        raise ValueError("Unsupported report schedule.")
    if schedule != "none" and "@" not in report_email:
        raise ValueError("A report email is required for scheduled delivery.")
    if alert_not_helpful_threshold is not None and not 0 <= alert_not_helpful_threshold <= 1:
        raise ValueError("Alert threshold must be between 0 and 1.")
    safe_filters = {str(key): str(value) for key, value in filters.items() if str(value).strip()}
    identifier = view_id or str(uuid4())
    with get_engine().begin() as connection:
        if view_id:
            owner = connection.execute(
                text("SELECT owner_sub FROM analytics_saved_views WHERE id = :id"),
                {"id": identifier},
            ).scalar()
            if owner and owner != owner_sub:
                raise PermissionError("This saved view belongs to another administrator.")
        row = connection.execute(
            text(
                """
                INSERT INTO analytics_saved_views (
                    id, name, owner_sub, filters, schedule, report_email,
                    alert_not_helpful_threshold, next_run_at
                ) VALUES (
                    :id, :name, :owner_sub, CAST(:filters AS JSONB), :schedule,
                    :report_email, :threshold, :next_run_at
                )
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    filters = EXCLUDED.filters,
                    schedule = EXCLUDED.schedule,
                    report_email = EXCLUDED.report_email,
                    alert_not_helpful_threshold = EXCLUDED.alert_not_helpful_threshold,
                    next_run_at = EXCLUDED.next_run_at,
                    updated_at = now()
                WHERE analytics_saved_views.owner_sub = EXCLUDED.owner_sub
                RETURNING *
                """
            ),
            {
                "id": identifier,
                "name": name.strip(),
                "owner_sub": owner_sub,
                "filters": json.dumps(safe_filters),
                "schedule": schedule,
                "report_email": report_email.strip().lower(),
                "threshold": alert_not_helpful_threshold,
                "next_run_at": _next_run(schedule),
            },
        ).mappings().one()
    result = dict(row)
    for field in ("last_sent_at", "next_run_at", "created_at", "updated_at"):
        result[field] = _iso(result.get(field))
    return result


def delete_saved_view(view_id: str, owner_sub: str) -> bool:
    """Delete one of the caller's saved analytics views."""
    with get_engine().begin() as connection:
        result = connection.execute(
            text("DELETE FROM analytics_saved_views WHERE id = :id AND owner_sub = :owner_sub"),
            {"id": view_id, "owner_sub": owner_sub},
        )
    return bool(result.rowcount)
