"""Database-managed support routing for the operations portal."""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

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
    actor_sub: str,
) -> dict[str, Any]:
    """Create or update a market support destination."""
    normalized_country = country.upper().strip()
    normalized_department = department.strip()
    normalized_email = email.strip().lower()
    if normalized_country not in get_country_codes():
        raise ValueError("Unsupported country.")
    if not normalized_department:
        raise ValueError("Department is required.")
    if not EMAIL_RE.fullmatch(normalized_email):
        raise ValueError("Enter a valid support email address.")

    with get_engine().begin() as connection:
        row = connection.execute(
            text(
                """
                INSERT INTO support_routes (
                    country, department, email, enabled, updated_by, created_at, updated_at
                ) VALUES (:country, :department, :email, :enabled, :actor, now(), now())
                ON CONFLICT (country) DO UPDATE SET
                    department = EXCLUDED.department,
                    email = EXCLUDED.email,
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
                    :country, jsonb_build_object('enabled', :enabled), now()
                )
                """
            ),
            {
                "event_id": str(uuid4()),
                "actor": actor_sub,
                "country": normalized_country,
                "enabled": enabled,
            },
        )
    return _serialize(dict(row))
