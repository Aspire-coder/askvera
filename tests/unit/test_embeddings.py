"""Tests for process-local and optional shared embedding caching."""

import io
import json

from config import settings
from services import embeddings


class _Runtime:
    def __init__(self):
        self.calls = 0
        self.model_ids = []

    def invoke_model(self, **kwargs):
        self.calls += 1
        self.model_ids.append(kwargs.get("modelId"))
        return {"body": io.BytesIO(json.dumps({"embedding": [0.1, 0.2]}).encode())}


class _Clients:
    def __init__(self, runtime):
        self.bedrock_runtime = runtime


class _Cache:
    def __init__(self, value=None):
        self.value = value
        self.writes = []

    def get(self, _key):
        return self.value

    def setex(self, key, ttl, value):
        self.writes.append((key, ttl, value))


def test_shared_embedding_cache_hit_skips_bedrock(monkeypatch) -> None:
    cache = _Cache(json.dumps([0.3, 0.4]))
    runtime = _Runtime()
    monkeypatch.setattr(settings, "EMBEDDING_SHARED_CACHE_ENABLED", True)
    monkeypatch.setattr(embeddings, "get_cache_client", lambda: cache)
    monkeypatch.setattr(embeddings, "get_aws_clients", lambda: _Clients(runtime))
    embeddings.embed_text.cache_clear()

    assert embeddings.embed_text("policy question") == [0.3, 0.4]
    assert runtime.calls == 0


def test_shared_embedding_cache_miss_writes_bedrock_result(monkeypatch) -> None:
    cache = _Cache()
    runtime = _Runtime()
    monkeypatch.setattr(settings, "EMBEDDING_SHARED_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "EMBEDDING_SHARED_CACHE_TTL_SECONDS", 60)
    monkeypatch.setattr(embeddings, "get_cache_client", lambda: cache)
    monkeypatch.setattr(embeddings, "get_aws_clients", lambda: _Clients(runtime))
    embeddings.embed_text.cache_clear()

    assert embeddings.embed_text("another question") == [0.1, 0.2]
    assert runtime.calls == 1
    assert cache.writes[0][1] == 60


def test_embedding_model_can_be_selected_for_semantic_cache(monkeypatch) -> None:
    runtime = _Runtime()
    monkeypatch.setattr(settings, "EMBEDDING_SHARED_CACHE_ENABLED", False)
    monkeypatch.setattr(embeddings, "get_aws_clients", lambda: _Clients(runtime))
    embeddings.embed_text.cache_clear()

    assert embeddings.embed_text("semantic question", model_id="amazon.example-embed:1") == [0.1, 0.2]
    assert runtime.model_ids == ["amazon.example-embed:1"]
