"""Tests for evidence-bound semantic answer caching."""

from __future__ import annotations

import json

import redis

from app.retrieval.models import RetrievedDocument, RetrievalResult
from services import semantic_cache


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.scores: dict[str, dict[str, float]] = {}
        self.ttls: dict[str, int] = {}

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value
        self.ttls[key] = ttl

    def zadd(self, key: str, values: dict[str, float]) -> None:
        self.scores.setdefault(key, {}).update(values)

    def expire(self, key: str, ttl: int) -> None:
        self.ttls[key] = ttl

    def zcard(self, key: str) -> int:
        return len(self.scores.get(key, {}))

    def zrange(self, key: str, start: int, stop: int) -> list[str]:
        members = sorted(self.scores.get(key, {}), key=self.scores[key].get)
        return members[start : stop + 1]

    def delete(self, *keys: str) -> None:
        for key in keys:
            self.values.pop(key, None)

    def zrem(self, key: str, *members: str) -> None:
        for member in members:
            self.scores.get(key, {}).pop(member, None)

    def zremrangebyscore(self, key: str, minimum: object, maximum: float) -> None:
        del minimum
        expired = [
            member
            for member, score in self.scores.get(key, {}).items()
            if score <= maximum
        ]
        self.zrem(key, *expired)

    def zrevrangebyscore(
        self, key: str, maximum: object, minimum: float, *, start: int, num: int
    ) -> list[str]:
        del maximum
        members = [
            member
            for member, score in self.scores.get(key, {}).items()
            if score >= minimum
        ]
        members.sort(key=self.scores[key].get, reverse=True)
        return members[start : start + num]

    def mget(self, keys: list[str]) -> list[str | None]:
        return [self.values.get(key) for key in keys]


def _result(*, version: str = "2026.1", country: str = "US") -> RetrievalResult:
    document = RetrievedDocument(
        id="policy:section-1",
        title="Company Policy",
        content="Recognized Manager requirements.",
        source="s3://approved/policy.pdf",
        document_version=version,
        country=country,
        language="en",
        metadata={"section_id": "section-1", "ingestion_id": "ing-1"},
    )
    return RetrievalResult(documents=[document], citations=[], confidence=0.9)


def _enable(monkeypatch, client: _FakeRedis) -> None:
    monkeypatch.setattr(semantic_cache.settings, "SEMANTIC_CACHE_ENABLED", True)
    monkeypatch.setattr(semantic_cache.settings, "SEMANTIC_CACHE_SHADOW_ENABLED", False)
    monkeypatch.setattr(semantic_cache.settings, "SEMANTIC_CACHE_THRESHOLD", 0.96)
    monkeypatch.setattr(
        semantic_cache.settings, "SEMANTIC_CACHE_MIN_SCORE_MARGIN", 0.02
    )
    monkeypatch.setattr(semantic_cache.settings, "SEMANTIC_CACHE_MAX_CANDIDATES", 64)
    monkeypatch.setattr(semantic_cache.settings, "SEMANTIC_CACHE_MAX_ENTRIES", 256)
    monkeypatch.setattr(semantic_cache.settings, "SEMANTIC_CACHE_TTL_SECONDS", 7200)
    monkeypatch.setattr(
        semantic_cache.settings, "SEMANTIC_CACHE_MAX_VECTOR_DIMENSIONS", 1536
    )
    monkeypatch.setattr(semantic_cache, "get_cache_client", lambda: client)


def test_shadow_mode_activates_storage_without_live_reuse(monkeypatch) -> None:
    monkeypatch.setattr(semantic_cache.settings, "SEMANTIC_CACHE_ENABLED", False)
    monkeypatch.setattr(semantic_cache.settings, "SEMANTIC_CACHE_SHADOW_ENABLED", True)

    assert semantic_cache.semantic_cache_active() is True


def test_evidence_fingerprint_is_order_independent_and_version_sensitive() -> None:
    first = _result()
    second_document = RetrievedDocument(
        id="directory:2",
        title="Directory",
        content="Office listing",
        source="s3://approved/directory.pdf",
        document_version="4",
    )
    reordered = RetrievalResult(
        documents=[second_document, first.documents[0]], citations=[], confidence=0.9
    )
    original = RetrievalResult(
        documents=[first.documents[0], second_document], citations=[], confidence=0.9
    )

    assert semantic_cache.evidence_fingerprint(
        original
    ) == semantic_cache.evidence_fingerprint(reordered)
    assert semantic_cache.evidence_fingerprint(
        first
    ) != semantic_cache.evidence_fingerprint(_result(version="2027.1"))


def test_semantic_cache_hit_requires_same_evidence(monkeypatch) -> None:
    client = _FakeRedis()
    _enable(monkeypatch, client)
    monkeypatch.setattr(semantic_cache, "_embedding", lambda _: [1.0, 0.0])
    response = {
        "response": "Use the approved manager steps.",
        "sources": [{"title": "Policy"}],
    }

    semantic_cache.set_semantic_cache_value(
        "recognized manager", "US", "en", "guest", _result(), response, "cid"
    )
    hit = semantic_cache.get_semantic_cache_value(
        "recognised manager", "US", "en", "guest", _result(), "cid"
    )
    stale = semantic_cache.get_semantic_cache_value(
        "recognised manager", "US", "en", "guest", _result(version="2027.1"), "cid"
    )

    assert hit is not None
    assert hit.response == response
    assert hit.similarity == 1.0
    assert stale is None


def test_semantic_cache_isolated_by_country_language_role_and_versions(
    monkeypatch,
) -> None:
    client = _FakeRedis()
    _enable(monkeypatch, client)

    us = semantic_cache._namespace("US", "en", "guest")
    canada = semantic_cache._namespace("CA", "en", "guest")
    french = semantic_cache._namespace("US", "fr", "guest")
    admin = semantic_cache._namespace("US", "en", "admin")
    monkeypatch.setattr(semantic_cache.settings, "PROMPT_VERSION", "changed")

    assert len({us, canada, french, admin}) == 4
    assert semantic_cache._namespace("US", "en", "guest") != us


def test_semantic_cache_rejects_low_score_and_ambiguous_answers(monkeypatch) -> None:
    client = _FakeRedis()
    _enable(monkeypatch, client)
    vectors = iter([[1.0, 0.0], [0.999, 0.045], [1.0, 0.0]])
    monkeypatch.setattr(semantic_cache, "_embedding", lambda _: next(vectors))
    semantic_cache.set_semantic_cache_value(
        "first", "US", "en", "guest", _result(), {"response": "Answer A"}, "cid"
    )
    semantic_cache.set_semantic_cache_value(
        "second", "US", "en", "guest", _result(), {"response": "Answer B"}, "cid"
    )

    assert (
        semantic_cache.get_semantic_cache_value(
            "question", "US", "en", "guest", _result(), "cid"
        )
        is None
    )

    monkeypatch.setattr(semantic_cache, "_embedding", lambda _: [0.0, 1.0])
    assert (
        semantic_cache.get_semantic_cache_value(
            "unrelated", "US", "en", "guest", _result(), "cid"
        )
        is None
    )


def test_semantic_cache_does_not_store_question_and_entries_expire_individually(
    monkeypatch,
) -> None:
    client = _FakeRedis()
    _enable(monkeypatch, client)
    monkeypatch.setattr(semantic_cache, "_embedding", lambda _: [1.0, 0.0])
    question = "private wording should not be retained"

    semantic_cache.set_semantic_cache_value(
        question, "US", "en", "guest", _result(), {"response": "Approved answer"}, "cid"
    )

    entry_values = [value for key, value in client.values.items() if ":entry:" in key]
    assert len(entry_values) == 1
    assert question not in entry_values[0]
    assert (
        json.loads(entry_values[0])["expires_at"]
        > json.loads(entry_values[0])["created_at"]
    )
    assert 7200 in client.ttls.values()


def test_semantic_cache_fails_open_when_embedding_or_redis_fails(monkeypatch) -> None:
    client = _FakeRedis()
    _enable(monkeypatch, client)
    monkeypatch.setattr(
        semantic_cache,
        "_embedding",
        lambda _: (_ for _ in ()).throw(RuntimeError("down")),
    )

    assert (
        semantic_cache.get_semantic_cache_value(
            "question", "US", "en", "guest", _result(), "cid"
        )
        is None
    )
    semantic_cache.set_semantic_cache_value(
        "question", "US", "en", "guest", _result(), {"response": "answer"}, "cid"
    )

    monkeypatch.setattr(semantic_cache, "_embedding", lambda _: [1.0, 0.0])
    monkeypatch.setattr(
        client,
        "zremrangebyscore",
        lambda *_: (_ for _ in ()).throw(redis.RedisError("down")),
    )
    assert (
        semantic_cache.get_semantic_cache_value(
            "question", "US", "en", "guest", _result(), "cid"
        )
        is None
    )


def test_semantic_cache_removes_dead_entries_and_trims_oldest(monkeypatch) -> None:
    client = _FakeRedis()
    _enable(monkeypatch, client)
    monkeypatch.setattr(semantic_cache.settings, "SEMANTIC_CACHE_MAX_ENTRIES", 1)
    monkeypatch.setattr(semantic_cache, "_embedding", lambda _: [1.0, 0.0])

    semantic_cache.set_semantic_cache_value(
        "first", "US", "en", "guest", _result(), {"response": "First"}, "cid"
    )
    semantic_cache.set_semantic_cache_value(
        "second", "US", "en", "guest", _result(), {"response": "Second"}, "cid"
    )
    namespace = semantic_cache._namespace("US", "en", "guest")
    assert client.zcard(namespace) == 1

    dead_key = f"{namespace}:entry:missing"
    client.zadd(namespace, {dead_key: 9999999999.0})
    hit = semantic_cache.get_semantic_cache_value(
        "second", "US", "en", "guest", _result(), "cid"
    )

    assert hit is not None
    assert dead_key not in client.scores[namespace]
