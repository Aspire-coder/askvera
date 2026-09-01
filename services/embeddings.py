"""Bedrock embedding helpers for app-owned retrieval."""

from __future__ import annotations

import json
import hashlib
from functools import lru_cache

from botocore.exceptions import BotoCoreError, ClientError
import redis

from config import settings
from services.aws_clients import get_aws_clients
from services.cache import get_cache_client
from utils.exceptions import AwsServiceError
from utils.logging import get_logger

LOGGER = get_logger("services.embeddings")


def _normalize_text(value: str) -> str:
    """Keep embedding input bounded and stable."""
    return " ".join(value.split())[:8000]


@lru_cache(maxsize=2048)
def embed_text(text: str, model_id: str | None = None) -> list[float]:
    """Create one semantic embedding using the configured Bedrock model."""
    normalized = _normalize_text(text)
    if not normalized:
        return []

    selected_model_id = model_id or settings.BEDROCK_EMBED_MODEL_ID
    shared_key = _shared_embedding_key(normalized, selected_model_id)
    shared_embedding = _get_shared_embedding(shared_key)
    if shared_embedding is not None:
        return shared_embedding

    payload = {"inputText": normalized}
    try:
        response = get_aws_clients().bedrock_runtime.invoke_model(
            modelId=selected_model_id,
            body=json.dumps(payload),
            contentType="application/json",
            accept="application/json",
        )
        body = json.loads(response["body"].read())
    except (BotoCoreError, ClientError, json.JSONDecodeError) as exc:
        LOGGER.exception("embedding_generation_failed")
        raise AwsServiceError("Embedding generation failed.") from exc

    embedding = body.get("embedding")
    if not isinstance(embedding, list):
        raise AwsServiceError("Embedding response did not include an embedding.")
    normalized_embedding = [float(value) for value in embedding]
    _set_shared_embedding(shared_key, normalized_embedding)
    return normalized_embedding


def _shared_embedding_key(normalized_text: str, model_id: str | None = None) -> str:
    digest = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
    selected_model_id = model_id or settings.BEDROCK_EMBED_MODEL_ID
    model_digest = hashlib.sha256(selected_model_id.encode("utf-8")).hexdigest()[:16]
    return f"{settings.EMBEDDING_SHARED_CACHE_PREFIX}:{model_digest}:{digest}"


def _get_shared_embedding(key: str) -> list[float] | None:
    if not settings.EMBEDDING_SHARED_CACHE_ENABLED:
        return None
    client = get_cache_client()
    if client is None:
        return None
    try:
        raw = client.get(key)
        if not raw:
            return None
        value = json.loads(raw)
        if not isinstance(value, list):
            return None
        return [float(item) for item in value]
    except (redis.RedisError, json.JSONDecodeError, TypeError, ValueError):
        LOGGER.exception("shared_embedding_cache_read_failed")
        return None


def _set_shared_embedding(key: str, embedding: list[float]) -> None:
    if not settings.EMBEDDING_SHARED_CACHE_ENABLED:
        return
    client = get_cache_client()
    if client is None:
        return
    try:
        client.setex(
            key,
            settings.EMBEDDING_SHARED_CACHE_TTL_SECONDS,
            json.dumps(embedding, separators=(",", ":")),
        )
    except redis.RedisError:
        LOGGER.exception("shared_embedding_cache_write_failed")
