"""Tests for shared rate-limit and token-revocation state."""

from time import time

import redis
import pytest

from services.security_state import SecurityState, SecurityStateUnavailable


class FakeRedis:
    def __init__(self) -> None:
        self.eval_result = 1
        self.values: dict[str, str] = {}
        self.expiries: dict[str, int] = {}

    def eval(self, _script, _key_count, _key, *_args):
        return self.eval_result

    def set(self, key, value, ex):
        self.values[key] = value
        self.expiries[key] = ex

    def exists(self, key):
        return int(key in self.values)


class FailingRedis:
    def eval(self, *_args):
        raise redis.RedisError("unavailable")


def test_local_rate_limit_fallback(monkeypatch) -> None:
    from services import security_state as module

    monkeypatch.setattr(module.settings, "SHARED_SECURITY_STATE_ENABLED", False)
    state = SecurityState()

    assert state.allow_request("203.0.113.10", "/api/chat", 1, 60)
    assert not state.allow_request("203.0.113.10", "/api/chat", 1, 60)


def test_valkey_rate_limit_result_is_used(monkeypatch) -> None:
    from services import security_state as module

    client = FakeRedis()
    monkeypatch.setattr(module.settings, "SHARED_SECURITY_STATE_ENABLED", True)
    monkeypatch.setattr(module, "get_cache_client", lambda: client)
    state = SecurityState()

    assert state.allow_request("203.0.113.10", "/api/chat", 2, 60)
    client.eval_result = 0
    assert not state.allow_request("203.0.113.10", "/api/chat", 2, 60)


def test_token_revocation_uses_bounded_valkey_ttl(monkeypatch) -> None:
    from services import security_state as module

    client = FakeRedis()
    monkeypatch.setattr(module.settings, "SHARED_SECURITY_STATE_ENABLED", True)
    monkeypatch.setattr(module.settings, "SHARED_SECURITY_STATE_PREFIX", "test-security")
    monkeypatch.setattr(module, "get_cache_client", lambda: client)
    state = SecurityState()

    state.revoke_widget_token("token-id", int(time()) + 120)

    assert state.is_widget_token_revoked("token-id")
    assert 1 <= next(iter(client.expiries.values())) <= 120
    assert "token-id" not in next(iter(client.values))


def test_required_shared_state_fails_closed(monkeypatch) -> None:
    from services import security_state as module

    monkeypatch.setattr(module.settings, "SHARED_SECURITY_STATE_ENABLED", True)
    monkeypatch.setattr(module.settings, "SHARED_SECURITY_STATE_REQUIRED", True)
    monkeypatch.setattr(module, "get_cache_client", lambda: FailingRedis())
    state = SecurityState()

    with pytest.raises(SecurityStateUnavailable):
        state.allow_request("203.0.113.10", "/api/chat", 2, 60)
