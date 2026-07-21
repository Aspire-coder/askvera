"""Shared rate-limit and widget-token revocation state."""

from __future__ import annotations

import hashlib
from collections import defaultdict, deque
from threading import RLock
from time import monotonic, time
from uuid import uuid4

import redis

from config import settings
from services.cache import get_cache_client
from utils.logging import get_logger

LOGGER = get_logger("services.security_state")


class SecurityStateUnavailable(RuntimeError):
    """Raised when production security state cannot be read or written."""


class SecurityState:
    """Use Valkey in production and a bounded process-local store in development."""

    _RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local cutoff = tonumber(ARGV[1])
local now = tonumber(ARGV[2])
local member = ARGV[3]
local limit = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])
redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)
local count = redis.call('ZCARD', key)
if count >= limit then
  redis.call('PEXPIRE', key, ttl)
  return 0
end
redis.call('ZADD', key, now, member)
redis.call('PEXPIRE', key, ttl)
return 1
"""

    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._revoked_tokens: dict[str, int] = {}
        self._lock = RLock()

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _client(self) -> redis.Redis | None:
        if not settings.SHARED_SECURITY_STATE_ENABLED:
            return None
        return get_cache_client()

    @staticmethod
    def _handle_redis_error(operation: str, exc: redis.RedisError) -> None:
        LOGGER.exception("shared_security_state_failed", operation=operation)
        if settings.SHARED_SECURITY_STATE_REQUIRED:
            raise SecurityStateUnavailable("Shared security state is temporarily unavailable.") from exc

    def allow_request(self, identity: str, path: str, limit: int, window_seconds: int) -> bool:
        """Return whether a request fits within the configured sliding window."""
        raw_key = f"{identity}:{path}"
        client = self._client()
        if client is not None:
            now_ms = int(time() * 1000)
            window_ms = max(1, window_seconds) * 1000
            key = f"{settings.SHARED_SECURITY_STATE_PREFIX}:rate:{self._digest(raw_key)}"
            try:
                allowed = client.eval(
                    self._RATE_LIMIT_SCRIPT,
                    1,
                    key,
                    now_ms - window_ms,
                    now_ms,
                    f"{now_ms}:{uuid4().hex}",
                    max(1, limit),
                    window_ms,
                )
                return bool(allowed)
            except redis.RedisError as exc:
                self._handle_redis_error("rate_limit", exc)

        return self._allow_request_locally(raw_key, limit, window_seconds)

    def _allow_request_locally(self, key: str, limit: int, window_seconds: int) -> bool:
        now = monotonic()
        window_start = now - max(1, window_seconds)
        with self._lock:
            history = self._requests[key]
            while history and history[0] < window_start:
                history.popleft()
            if len(history) >= max(1, limit):
                return False
            history.append(now)
            return True

    def revoke_widget_token(self, jti: str, expires_at: int | None = None) -> None:
        """Revoke a token ID until its JWT expiry time."""
        if not jti:
            return
        expiry = expires_at or (int(time()) + settings.WIDGET_JWT_TTL_SECONDS)
        ttl = max(1, expiry - int(time()))
        client = self._client()
        if client is not None:
            key = f"{settings.SHARED_SECURITY_STATE_PREFIX}:revoked:{self._digest(jti)}"
            try:
                client.set(key, "1", ex=ttl)
                return
            except redis.RedisError as exc:
                self._handle_redis_error("token_revoke", exc)

        with self._lock:
            self._prune_revocations()
            self._revoked_tokens[jti] = expiry

    def is_widget_token_revoked(self, jti: str | None) -> bool:
        """Return True when a token ID is present in shared revocation state."""
        if not jti:
            return False
        client = self._client()
        if client is not None:
            key = f"{settings.SHARED_SECURITY_STATE_PREFIX}:revoked:{self._digest(jti)}"
            try:
                return bool(client.exists(key))
            except redis.RedisError as exc:
                self._handle_redis_error("token_check", exc)

        with self._lock:
            self._prune_revocations()
            return jti in self._revoked_tokens

    def _prune_revocations(self) -> None:
        now = int(time())
        expired = [jti for jti, expiry in self._revoked_tokens.items() if expiry <= now]
        for jti in expired:
            self._revoked_tokens.pop(jti, None)

    def reset_local_state(self) -> None:
        """Clear process-local state for isolated tests."""
        with self._lock:
            self._requests.clear()
            self._revoked_tokens.clear()


security_state = SecurityState()
