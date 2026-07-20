"""Unit tests for Redis cache keying and read/write behavior."""

from unittest.mock import MagicMock

from services import cache


def test_build_cache_key_is_role_and_locale_aware() -> None:
    """Cache key changes when role changes."""
    first = cache.build_cache_key("hello", "US", "en", "new_prospect")
    second = cache.build_cache_key("hello", "US", "en", "active_distributor")
    assert first != second
    assert first.startswith("ask-vera:US:en:new_prospect:")


def test_build_cache_key_is_version_aware(monkeypatch) -> None:
    """Cache keys rotate when prompt or knowledge-base versions change."""
    first = cache.build_cache_key("hello", "US", "en", "new_prospect")
    monkeypatch.setattr(cache.settings, "KB_VERSION", "next-version")
    second = cache.build_cache_key("hello", "US", "en", "new_prospect")
    assert first != second


def test_get_and_set_cache_value(monkeypatch) -> None:
    """Cache values are JSON encoded and decoded."""
    client = MagicMock()
    client.get.return_value = '{"response": "ok"}'
    monkeypatch.setattr(cache, "_redis_client", client)
    assert cache.get_cache_value("k", "cid") == {"response": "ok"}
    cache.set_cache_value("k", {"response": "ok"}, "cid")
    client.setex.assert_called_once()


def test_cache_health_reports_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(cache, "_redis_client", None)

    assert cache.cache_health() == "not_configured"


def test_cache_health_pings_configured_client(monkeypatch) -> None:
    client = MagicMock()
    monkeypatch.setattr(cache, "_redis_client", client)

    assert cache.cache_health() == "healthy"
    client.ping.assert_called_once_with()
