"""Unit tests for market configuration loading and validation."""

import json

import pytest
from pydantic import ValidationError

from services import market_config
from utils.validators import ChatRequest


def _write_config(tmp_path, markets):
    config_path = tmp_path / "markets.json"
    config_path.write_text(json.dumps({"version": 1, "markets": markets}), encoding="utf-8")
    return config_path


def _market(code="CA", languages=None, default_language="en", enabled=True, display_order=10):
    return {
        "code": code,
        "name": "Canada",
        "enabled": enabled,
        "defaultLanguage": default_language,
        "privacyVersion": "2026.1",
        "displayOrder": display_order,
        "languages": languages
        or [
            {"code": "en", "name": "English", "enabled": True},
            {"code": "fr", "name": "French", "enabled": True},
        ],
    }


def test_load_market_config_hides_disabled_markets_and_languages(tmp_path, monkeypatch) -> None:
    """Only enabled market/language options are exposed to the API."""
    config_path = _write_config(
        tmp_path,
        [
            _market(languages=[{"code": "en", "name": "English", "enabled": True}, {"code": "fr", "name": "French", "enabled": False}]),
            _market(code="US", enabled=False, display_order=20),
        ],
    )
    monkeypatch.setenv("MARKETS_CONFIG_PATH", str(config_path))
    market_config.load_market_config.cache_clear()

    countries = market_config.get_countries()

    assert [country["code"] for country in countries] == ["CA"]
    assert countries[0]["languages"] == [{"code": "en", "name": "English"}]


def test_load_market_config_rejects_duplicate_market_codes(tmp_path, monkeypatch) -> None:
    """Duplicate market codes fail fast at config load time."""
    config_path = _write_config(tmp_path, [_market(), _market()])
    monkeypatch.setenv("MARKETS_CONFIG_PATH", str(config_path))
    market_config.load_market_config.cache_clear()

    with pytest.raises(RuntimeError, match="duplicate market code CA"):
        market_config.load_market_config()


def test_load_market_config_rejects_duplicate_language_codes(tmp_path, monkeypatch) -> None:
    """Duplicate language codes within one market fail fast."""
    config_path = _write_config(
        tmp_path,
        [
            _market(
                languages=[
                    {"code": "en", "name": "English", "enabled": True},
                    {"code": "en", "name": "English duplicate", "enabled": True},
                ]
            )
        ],
    )
    monkeypatch.setenv("MARKETS_CONFIG_PATH", str(config_path))
    market_config.load_market_config.cache_clear()

    with pytest.raises(RuntimeError, match="duplicate language en in CA"):
        market_config.load_market_config()


def test_load_market_config_rejects_default_language_not_enabled(tmp_path, monkeypatch) -> None:
    """A market's default language must be one of its enabled language options."""
    config_path = _write_config(
        tmp_path,
        [_market(languages=[{"code": "en", "name": "English", "enabled": True}], default_language="fr")],
    )
    monkeypatch.setenv("MARKETS_CONFIG_PATH", str(config_path))
    market_config.load_market_config.cache_clear()

    with pytest.raises(RuntimeError, match="CA.defaultLanguage"):
        market_config.load_market_config()


def test_public_markets_are_limited_to_published_policy_locales() -> None:
    """The public picker exposes only country/language pairs with published policies."""
    market_config.load_market_config.cache_clear()
    market_config.load_policy_locales.cache_clear()

    countries = {country["code"]: country for country in market_config.get_countries()}

    assert set(countries) == {
        "AT",
        "BE",
        "CA",
        "CH",
        "DE",
        "DK",
        "FI",
        "GB",
        "IT",
        "LU",
        "NL",
        "NO",
        "SE",
        "US",
    }
    assert countries["CH"]["languages"] == [{"code": "de", "name": "German"}]
    assert countries["CH"]["defaultLanguage"] == "de"
    assert countries["SE"]["languages"] == [
        {"code": "en", "name": "English"},
        {"code": "sv", "name": "Swedish"},
    ]
    assert countries["SE"]["defaultLanguage"] == "en"
    assert market_config.get_document_country_codes("GB") == {"GB", "UK"}


def test_chat_request_accepts_published_sweden_languages() -> None:
    """Sweden accepts only the two company-policy languages being published."""
    market_config.load_market_config.cache_clear()
    market_config.load_policy_locales.cache_clear()

    for language in ("en", "sv"):
        request = ChatRequest(
            message="How do I become a Recognized Manager?",
            sessionId=f"sweden-{language}",
            country="SE",
            language=language,
        )
        assert request.country == "SE"
        assert request.language == language


def test_chat_request_rejects_unpublished_language_for_market() -> None:
    """A missing source language must not silently fall back to another language."""
    market_config.load_market_config.cache_clear()
    market_config.load_policy_locales.cache_clear()

    with pytest.raises(ValidationError, match="Unsupported language for country"):
        ChatRequest(
            message="Vad är en aktiv FBO?",
            sessionId="session-1",
            country="FI",
            language="sv",
        )
