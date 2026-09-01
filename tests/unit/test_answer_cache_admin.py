"""Safety tests for the Operations answer-cache reset."""

from fnmatch import fnmatch

import pytest
import redis

from services import answer_cache_admin


class FakeRedis:
    def __init__(self, keys: set[str]) -> None:
        self.keys = set(keys)

    def scan_iter(self, match: str, count: int = 0):
        del count
        yield from sorted(key for key in self.keys if fnmatch(key, match))

    def unlink(self, *keys: str) -> int:
        deleted = sum(key in self.keys for key in keys)
        self.keys.difference_update(keys)
        return deleted


def _exact(country: str, suffix: str = "a") -> str:
    return f"ask-vera:{country}:en:customer:{suffix * 64}"


def _semantic(country: str, suffix: str = "b") -> tuple[str, str]:
    namespace = f"ask-vera:semantic:{country.lower()}:en:customer:{suffix * 20}"
    return namespace, f"{namespace}:entry:{suffix * 64}"


def test_country_reset_deletes_only_matching_answer_keys(monkeypatch) -> None:
    us_semantic, us_entry = _semantic("US")
    ca_semantic, ca_entry = _semantic("CA", "c")
    client = FakeRedis({
        _exact("US"),
        _exact("CA", "d"),
        us_semantic,
        us_entry,
        ca_semantic,
        ca_entry,
        "ask-vera:security:rate-limit:US:abc",
        f"ask-vera:security:en:customer:{'e' * 64}",
        "ask-vera:model-circuit:claude",
        "ask-vera:widget-registry:active",
        "ask-vera:US:en:customer:not-a-valid-answer-key",
    })
    monkeypatch.setattr(answer_cache_admin, "get_cache_client", lambda: client)
    monkeypatch.setattr(answer_cache_admin, "get_country_codes", lambda: {"US", "CA"})
    monkeypatch.setattr(answer_cache_admin, "get_widget_country_codes", lambda: {"US", "CA"})

    result = answer_cache_admin.reset_answer_cache(
        "us", include_semantic=True, correlation_id="test"
    )

    assert result["exact_deleted"] == 1
    assert result["semantic_deleted"] == 2
    assert result["total_deleted"] == 3
    assert _exact("CA", "d") in client.keys
    assert ca_semantic in client.keys and ca_entry in client.keys
    assert "ask-vera:security:rate-limit:US:abc" in client.keys
    assert f"ask-vera:security:en:customer:{'e' * 64}" in client.keys
    assert "ask-vera:model-circuit:claude" in client.keys
    assert "ask-vera:widget-registry:active" in client.keys
    assert "ask-vera:US:en:customer:not-a-valid-answer-key" in client.keys


def test_all_market_exact_reset_does_not_delete_semantic_or_security(monkeypatch) -> None:
    us_semantic, us_entry = _semantic("US")
    client = FakeRedis({
        _exact("US"),
        _exact("CA", "d"),
        us_semantic,
        us_entry,
        "ask-vera:security:revoked-token:abc",
    })
    monkeypatch.setattr(answer_cache_admin, "get_cache_client", lambda: client)
    monkeypatch.setattr(answer_cache_admin, "get_country_codes", lambda: {"US", "CA"})
    monkeypatch.setattr(answer_cache_admin, "get_widget_country_codes", lambda: {"US", "CA"})

    result = answer_cache_admin.reset_answer_cache(
        "ALL", include_semantic=False, correlation_id="test"
    )

    assert result["exact_deleted"] == 2
    assert result["semantic_deleted"] == 0
    assert us_semantic in client.keys and us_entry in client.keys
    assert "ask-vera:security:revoked-token:abc" in client.keys


def test_reset_fails_closed_when_cache_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(answer_cache_admin, "get_cache_client", lambda: None)
    monkeypatch.setattr(answer_cache_admin, "get_country_codes", lambda: {"US"})
    monkeypatch.setattr(answer_cache_admin, "get_widget_country_codes", lambda: {"US"})

    with pytest.raises(answer_cache_admin.AnswerCacheUnavailable):
        answer_cache_admin.reset_answer_cache(
            "US", include_semantic=True, correlation_id="test"
        )


def test_reset_maps_redis_failures_to_safe_error(monkeypatch) -> None:
    class BrokenRedis:
        def scan_iter(self, **_kwargs):
            raise redis.RedisError("unavailable")

    monkeypatch.setattr(answer_cache_admin, "get_cache_client", lambda: BrokenRedis())
    monkeypatch.setattr(answer_cache_admin, "get_country_codes", lambda: {"US"})
    monkeypatch.setattr(answer_cache_admin, "get_widget_country_codes", lambda: {"US"})

    with pytest.raises(answer_cache_admin.AnswerCacheUnavailable):
        answer_cache_admin.reset_answer_cache(
            "US", include_semantic=True, correlation_id="test"
        )
