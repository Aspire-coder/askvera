"""Market and language configuration loaded from JSON."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_MARKETS_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "markets.json"
REQUIRED_MARKET_FIELDS = {"code", "name", "enabled", "defaultLanguage", "languages", "privacyVersion", "displayOrder"}
REQUIRED_LANGUAGE_FIELDS = {"code", "name", "enabled"}


def _config_path() -> Path:
    try:
        from config import settings

        configured_path = getattr(settings, "MARKETS_CONFIG_PATH", None)
    except ImportError:
        configured_path = None
    return Path(os.environ.get("MARKETS_CONFIG_PATH", configured_path or DEFAULT_MARKETS_CONFIG_PATH))


@lru_cache(maxsize=1)
def load_market_config() -> dict[str, Any]:
    """Load the market configuration file once per process."""
    config_path = _config_path()
    with config_path.open("r", encoding="utf-8") as file:
        config = json.load(file)
    _validate_market_config(config, config_path)
    return config


def _validate_market_config(config: dict[str, Any], config_path: Path) -> None:
    """Fail fast when markets.json is malformed."""
    markets = config.get("markets")
    if not isinstance(markets, list) or not markets:
        raise RuntimeError(f"Invalid market config: {config_path} must contain a non-empty markets list.")

    seen_market_codes: set[str] = set()
    seen_display_orders: set[int] = set()
    for index, market in enumerate(markets):
        if not isinstance(market, dict):
            raise RuntimeError(f"Invalid market config: market #{index + 1} must be an object.")

        missing_market_fields = REQUIRED_MARKET_FIELDS - set(market)
        if missing_market_fields:
            raise RuntimeError(
                f"Invalid market config: market #{index + 1} is missing {', '.join(sorted(missing_market_fields))}."
            )

        code = str(market["code"]).upper()
        if code in seen_market_codes:
            raise RuntimeError(f"Invalid market config: duplicate market code {code}.")
        seen_market_codes.add(code)

        if not isinstance(market["enabled"], bool):
            raise RuntimeError(f"Invalid market config: {code}.enabled must be true or false.")
        if not isinstance(market["displayOrder"], int):
            raise RuntimeError(f"Invalid market config: {code}.displayOrder must be a number.")
        if market["displayOrder"] in seen_display_orders:
            raise RuntimeError(f"Invalid market config: duplicate displayOrder {market['displayOrder']}.")
        seen_display_orders.add(market["displayOrder"])

        languages = market["languages"]
        if not isinstance(languages, list) or not languages:
            raise RuntimeError(f"Invalid market config: {code}.languages must be a non-empty list.")

        default_language = str(market["defaultLanguage"])
        enabled_language_codes: set[str] = set()
        all_language_codes: set[str] = set()
        for language_index, language in enumerate(languages):
            if not isinstance(language, dict):
                raise RuntimeError(f"Invalid market config: {code}.languages[{language_index}] must be an object.")

            missing_language_fields = REQUIRED_LANGUAGE_FIELDS - set(language)
            if missing_language_fields:
                raise RuntimeError(
                    f"Invalid market config: {code}.languages[{language_index}] is missing "
                    f"{', '.join(sorted(missing_language_fields))}."
                )

            language_code = str(language["code"])
            if language_code in all_language_codes:
                raise RuntimeError(f"Invalid market config: duplicate language {language_code} in {code}.")
            all_language_codes.add(language_code)

            if not isinstance(language["enabled"], bool):
                raise RuntimeError(f"Invalid market config: {code}.{language_code}.enabled must be true or false.")
            if language["enabled"]:
                enabled_language_codes.add(language_code)

        if market["enabled"] and default_language not in enabled_language_codes:
            raise RuntimeError(
                f"Invalid market config: {code}.defaultLanguage must match an enabled language for that market."
            )


def get_markets() -> list[dict[str, Any]]:
    """Return enabled market objects in display order."""
    markets = load_market_config()["markets"]
    enabled_markets = [market for market in markets if market.get("enabled", True)]
    return sorted(enabled_markets, key=lambda market: (market.get("displayOrder", 9999), market.get("name", "")))


def get_countries() -> list[dict[str, Any]]:
    """Return the country/language shape expected by the public API."""
    countries: list[dict[str, Any]] = []
    for market in get_markets():
        languages = [
            {"code": language["code"], "name": language["name"]}
            for language in market.get("languages", [])
            if language.get("enabled", True)
        ]
        if languages:
            countries.append(
                {
                    "code": market["code"],
                    "name": market["name"],
                    "defaultLanguage": market["defaultLanguage"],
                    "privacyVersion": market["privacyVersion"],
                    "displayOrder": market["displayOrder"],
                    "languages": languages,
                }
            )
    return countries


def get_country_codes() -> set[str]:
    """Return enabled market codes."""
    return {country["code"] for country in get_countries()}


def get_language_codes_for_country(country_code: str) -> set[str]:
    """Return enabled language codes for a specific market."""
    normalized_code = country_code.upper()
    for country in get_countries():
        if country["code"] == normalized_code:
            return {language["code"] for language in country["languages"]}
    return set()
