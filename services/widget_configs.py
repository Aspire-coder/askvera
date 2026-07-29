"""RDS persistence and public embed generation for managed widget instances."""

from __future__ import annotations

import json
import re
import secrets
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import text

from app.widget_auth.origin_validator import normalize_origin
from config import settings
from services.db import get_engine
from services.market_config import get_country_codes, get_language_codes_for_country

HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
POSITIONS = {"bottom-right", "bottom-left"}
RATE_LIMIT_TIERS = {"standard", "low", "high"}


def _validated_origins(values: dict[str, Any]) -> list[str]:
    origins: list[str] = []
    for origin in values.get("allowed_origins") or []:
        raw_origin = str(origin).strip()
        parsed = urlparse(raw_origin)
        normalized = normalize_origin(raw_origin)
        if (
            not normalized
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(f"Invalid allowed origin: {origin}")
        origins.append(normalized)
    if len(set(origins)) != len(origins):
        raise ValueError("Allowed origins must be unique.")
    if not origins:
        raise ValueError("Add at least one allowed origin.")
    return origins


def _validated_locale(values: dict[str, Any]) -> tuple[list[str], list[str], str, str]:
    known_markets = get_country_codes()
    markets = sorted({str(value).upper() for value in values.get("markets") or []})
    if not markets or any(market not in known_markets for market in markets):
        raise ValueError("Choose one or more supported markets.")
    languages = sorted({str(value).lower() for value in values.get("languages") or []})
    valid_languages = set().union(*(get_language_codes_for_country(market) for market in markets))
    if not languages or any(language not in valid_languages for language in languages):
        raise ValueError("Choose languages supported by the selected markets.")
    default_market = str(values.get("default_market") or "").upper()
    default_language = str(values.get("default_language") or "").lower()
    if default_market not in markets:
        raise ValueError("Default market must be in the allowed market list.")
    if default_language not in languages or default_language not in get_language_codes_for_country(default_market):
        raise ValueError("Default language must be valid for the default market.")
    return markets, languages, default_market, default_language


def _validated_presentation(values: dict[str, Any]) -> tuple[str, str, str]:
    accent_color = str(values.get("accent_color") or "#2F7D4E")
    if not HEX_COLOR_RE.fullmatch(accent_color):
        raise ValueError("Accent color must be a six-digit hex color.")
    position = str(values.get("position") or "bottom-right")
    if position not in POSITIONS:
        raise ValueError("Unsupported widget position.")
    logo_url = str(values.get("logo_url") or "").strip()
    if logo_url:
        asset_base = settings.WIDGET_ASSET_PUBLIC_BASE_URL.rstrip("/")
        if not asset_base or not logo_url.startswith(f"{asset_base}/"):
            raise ValueError("Widget logo must be an uploaded AskVera asset.")
    return accent_color, position, logo_url


def validate_widget_config(values: dict[str, Any]) -> dict[str, Any]:
    if not str(values.get("name") or "").strip():
        raise ValueError("Widget name is required.")
    origins = _validated_origins(values)
    markets, languages, default_market, default_language = _validated_locale(values)
    accent_color, position, logo_url = _validated_presentation(values)
    tier = str(values.get("rate_limit_tier") or "standard")
    if tier not in RATE_LIMIT_TIERS:
        raise ValueError("Unsupported rate-limit tier.")
    usage_cap = values.get("usage_cap")
    if usage_cap is not None and int(usage_cap) < 1:
        raise ValueError("Usage cap must be a positive number.")
    legal_version = str(values.get("legal_version") or settings.LEGAL_VERSION).strip()
    if legal_version != settings.LEGAL_VERSION:
        raise ValueError("Legal version must match the currently deployed consent version.")
    return {
        **values,
        "allowed_origins": origins,
        "markets": markets,
        "languages": languages,
        "default_market": default_market,
        "default_language": default_language,
        "accent_color": accent_color,
        "position": position,
        "legal_version": legal_version,
        "rate_limit_tier": tier,
        "usage_cap": int(usage_cap) if usage_cap is not None else None,
        "logo_url": logo_url,
    }


def _public_key() -> str:
    return f"wgt_{secrets.token_urlsafe(18)}"


def _write_audit(connection: Any, actor_sub: str, action: str, widget_id: str) -> None:
    connection.execute(
        text(
            """
            INSERT INTO admin_audit_log (
                event_id, actor_sub, action, target_type, target_id, metadata, created_at
            ) VALUES (
                :event_id, :actor_sub, :action, 'widget_config', :target_id, '{}'::jsonb, now()
            )
            """
        ),
        {
            "event_id": str(uuid4()),
            "actor_sub": actor_sub,
            "action": action,
            "target_id": widget_id,
        },
    )


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else "",
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else "",
        "embed_code": widget_embed_code(str(row["public_key"]), str(row.get("position") or "bottom-right")),
    }


def widget_embed_code(public_key: str, position: str = "bottom-right") -> str:
    """Return a public-only installation snippet with no credential material."""
    return (
        f'<link rel="stylesheet" href="{settings.WIDGET_STYLES_URL}">\n'
        f'<script src="{settings.WIDGET_LOADER_URL}"></script>\n'
        "<script>\n"
        f'  AskVera.init({{ widgetId: "{public_key}", apiUrl: "https://{settings.API_DOMAIN}", '
        f'position: "{position}" }});\n'
        "</script>"
    )


def list_widget_configs() -> list[dict[str, Any]]:
    with get_engine().connect() as connection:
        rows = connection.execute(text("SELECT * FROM widget_configs ORDER BY updated_at DESC")).mappings()
        return [_serialize(dict(row)) for row in rows]


def get_widget_config(identifier: str, *, public: bool = False) -> dict[str, Any] | None:
    column = "public_key" if public else "id"
    with get_engine().connect() as connection:
        row = connection.execute(
            text(f"SELECT * FROM widget_configs WHERE {column} = :identifier"),
            {"identifier": identifier},
        ).mappings().first()
    return _serialize(dict(row)) if row else None


def create_widget_config(values: dict[str, Any], actor_sub: str) -> dict[str, Any]:
    clean = validate_widget_config(values)
    widget_id = str(uuid4())
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO widget_configs (
                    id, name, customer, allowed_origins, markets, languages,
                    default_market, default_language, display_name, greeting,
                    logo_url, accent_color, position, legal_version, rate_limit_tier,
                    usage_cap, public_key, key_version, status, created_by,
                    created_at, updated_at
                ) VALUES (
                    :id, :name, :customer, CAST(:allowed_origins AS jsonb),
                    CAST(:markets AS jsonb), CAST(:languages AS jsonb),
                    :default_market, :default_language, :display_name, :greeting,
                    :logo_url, :accent_color, :position, :legal_version, :rate_limit_tier,
                    :usage_cap, :public_key, 1, 'active', :created_by, now(), now()
                )
                """
            ),
            {
                **clean,
                "id": widget_id,
                "name": str(clean.get("name") or "").strip(),
                "customer": str(clean.get("customer") or "").strip(),
                "display_name": str(clean.get("display_name") or "AskVera").strip(),
                "greeting": str(clean.get("greeting") or "").strip(),
                "legal_version": clean["legal_version"],
                "allowed_origins": json.dumps(clean["allowed_origins"]),
                "markets": json.dumps(clean["markets"]),
                "languages": json.dumps(clean["languages"]),
                "public_key": _public_key(),
                "created_by": actor_sub,
            },
        )
        _write_audit(connection, actor_sub, "widget_config.created", widget_id)
    return get_widget_config(widget_id) or {}


def update_widget_config(widget_id: str, values: dict[str, Any], actor_sub: str) -> dict[str, Any]:
    current = get_widget_config(widget_id)
    if not current:
        raise KeyError(widget_id)
    clean = validate_widget_config({**current, **values})
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                UPDATE widget_configs SET
                    name = :name, customer = :customer,
                    allowed_origins = CAST(:allowed_origins AS jsonb),
                    markets = CAST(:markets AS jsonb),
                    languages = CAST(:languages AS jsonb),
                    default_market = :default_market,
                    default_language = :default_language,
                    display_name = :display_name, greeting = :greeting, logo_url = :logo_url,
                    accent_color = :accent_color, position = :position,
                    legal_version = :legal_version, rate_limit_tier = :rate_limit_tier,
                    usage_cap = :usage_cap, updated_at = now()
                WHERE id = :id
                """
            ),
            {
                **clean,
                "id": widget_id,
                "name": str(clean.get("name") or "").strip(),
                "customer": str(clean.get("customer") or "").strip(),
                "display_name": str(clean.get("display_name") or "AskVera").strip(),
                "greeting": str(clean.get("greeting") or "").strip(),
                "legal_version": clean["legal_version"],
                "allowed_origins": json.dumps(clean["allowed_origins"]),
                "markets": json.dumps(clean["markets"]),
                "languages": json.dumps(clean["languages"]),
            },
        )
        _write_audit(connection, actor_sub, "widget_config.updated", widget_id)
    return get_widget_config(widget_id) or {}


def rotate_widget_key(widget_id: str, actor_sub: str) -> dict[str, Any]:
    with get_engine().begin() as connection:
        result = connection.execute(
            text(
                """
                UPDATE widget_configs
                SET public_key = :public_key, key_version = key_version + 1, updated_at = now()
                WHERE id = :id
                """
            ),
            {"id": widget_id, "public_key": _public_key()},
        )
        if result.rowcount == 0:
            raise KeyError(widget_id)
        _write_audit(connection, actor_sub, "widget_config.key_rotated", widget_id)
    return get_widget_config(widget_id) or {}


def disable_widget_config(widget_id: str, actor_sub: str) -> dict[str, Any]:
    with get_engine().begin() as connection:
        result = connection.execute(
            text("UPDATE widget_configs SET status = 'disabled', updated_at = now() WHERE id = :id"),
            {"id": widget_id},
        )
        if result.rowcount == 0:
            raise KeyError(widget_id)
        _write_audit(connection, actor_sub, "widget_config.disabled", widget_id)
    return get_widget_config(widget_id) or {}
