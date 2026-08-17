"""Database-managed support routing for the operations portal."""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from botocore.exceptions import BotoCoreError, ClientError

from config import settings
from services.aws_clients import get_aws_clients
from services.db import get_engine
from services.market_config import get_country_codes

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else "",
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else "",
    }


def list_support_routes() -> list[dict[str, Any]]:
    """Return all editable market routes."""
    try:
        with get_engine().connect() as connection:
            rows = connection.execute(
                text("SELECT * FROM support_routes ORDER BY country")
            ).mappings()
            return [_serialize(dict(row)) for row in rows]
    except SQLAlchemyError:
        return []


def get_active_support_route(country: str) -> dict[str, Any] | None:
    """Return one active route without exposing it through the widget API."""
    try:
        with get_engine().connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT * FROM support_routes
                    WHERE country = :country AND enabled = true
                    """
                ),
                {"country": country.upper()},
            ).mappings().first()
    except SQLAlchemyError:
        return None
    return _serialize(dict(row)) if row else None


def upsert_support_route(
    country: str,
    *,
    department: str,
    email: str,
    enabled: bool,
    fallback_department: str = "",
    fallback_email: str = "",
    actor_sub: str,
) -> dict[str, Any]:
    """Create or update a market support destination."""
    normalized_country = country.upper().strip()
    normalized_department = department.strip()
    normalized_email = email.strip().lower()
    normalized_fallback_department = fallback_department.strip()
    normalized_fallback_email = fallback_email.strip().lower()
    if normalized_country not in get_country_codes():
        raise ValueError("Unsupported country.")
    if not normalized_department:
        raise ValueError("Department is required.")
    if not EMAIL_RE.fullmatch(normalized_email):
        raise ValueError("Enter a valid support email address.")
    if bool(normalized_fallback_department) != bool(normalized_fallback_email):
        raise ValueError("Enter both fallback department and fallback email, or leave both blank.")
    if normalized_fallback_email and not EMAIL_RE.fullmatch(normalized_fallback_email):
        raise ValueError("Enter a valid fallback email address.")

    with get_engine().begin() as connection:
        previous = connection.execute(
            text("SELECT department, email, fallback_department, fallback_email, enabled FROM support_routes WHERE country = :country"),
            {"country": normalized_country},
        ).mappings().first()
        row = connection.execute(
            text(
                """
                INSERT INTO support_routes (
                    country, department, email, fallback_department, fallback_email,
                    enabled, updated_by, created_at, updated_at
                ) VALUES (:country, :department, :email, :fallback_department, :fallback_email, :enabled, :actor, now(), now())
                ON CONFLICT (country) DO UPDATE SET
                    department = EXCLUDED.department,
                    email = EXCLUDED.email,
                    fallback_department = EXCLUDED.fallback_department,
                    fallback_email = EXCLUDED.fallback_email,
                    enabled = EXCLUDED.enabled,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = now()
                RETURNING *
                """
            ),
            {
                "country": normalized_country,
                "department": normalized_department,
                "email": normalized_email,
                "fallback_department": normalized_fallback_department,
                "fallback_email": normalized_fallback_email,
                "enabled": enabled,
                "actor": actor_sub,
            },
        ).mappings().one()
        connection.execute(
            text(
                """
                INSERT INTO admin_audit_log (
                    event_id, actor_sub, action, target_type, target_id, metadata, created_at
                ) VALUES (
                    :event_id, :actor, 'support_route.updated', 'support_route',
                    :country, CAST(:metadata AS jsonb), now()
                )
                """
            ),
            {
                "event_id": str(uuid4()),
                "actor": actor_sub,
                "country": normalized_country,
                "metadata": json.dumps({
                    "before": dict(previous) if previous else None,
                    "after": {
                        "department": normalized_department,
                        "email": normalized_email,
                        "fallback_department": normalized_fallback_department,
                        "fallback_email": normalized_fallback_email,
                        "enabled": enabled,
                    },
                }),
            },
        )
    return _serialize(dict(row))


def support_route_history(country: str, limit: int = 50) -> list[dict[str, Any]]:
    with get_engine().connect() as connection:
        rows = connection.execute(
            text("SELECT event_id, actor_sub, action, metadata, created_at FROM admin_audit_log WHERE target_type = 'support_route' AND target_id = :country ORDER BY created_at DESC LIMIT :limit"),
            {"country": country.upper(), "limit": max(1, min(limit, 100))},
        ).mappings().all()
    return [{**dict(row), "created_at": row["created_at"].isoformat()} for row in rows]


def send_support_route_test(country: str) -> dict[str, str]:
    route = get_active_support_route(country)
    if not route or not settings.SUPPORT_EMAIL_ENABLED or not settings.SUPPORT_EMAIL_FROM:
        raise ValueError("This route or support email delivery is not enabled.")
    try:
        result = get_aws_clients().ses.send_email(
            Source=settings.SUPPORT_EMAIL_FROM,
            Destination={"ToAddresses": [str(route["email"])]},
            Message={
                "Subject": {"Data": f"AskVera route test - {country.upper()}", "Charset": "UTF-8"},
                "Body": {"Text": {"Data": "This is an administrator-requested AskVera support routing test. No customer data is included.", "Charset": "UTF-8"}},
            },
        )
    except (BotoCoreError, ClientError) as exc:
        raise RuntimeError("The route test could not be submitted to email delivery.") from exc
    return {"status": "submitted", "message_id": str(result.get("MessageId") or "")}
