"""Bedrock embedding helpers for app-owned retrieval."""

from __future__ import annotations

import json
from functools import lru_cache

from botocore.exceptions import BotoCoreError, ClientError

from config import settings
from services.aws_clients import get_aws_clients
from utils.exceptions import AwsServiceError
from utils.logging import get_logger

LOGGER = get_logger("services.embeddings")


def _normalize_text(value: str) -> str:
    """Keep embedding input bounded and stable."""
    return " ".join(value.split())[:8000]


@lru_cache(maxsize=2048)
def embed_text(text: str) -> list[float]:
    """Create one semantic embedding using the configured Bedrock model."""
    normalized = _normalize_text(text)
    if not normalized:
        return []

    payload = {"inputText": normalized}
    try:
        response = get_aws_clients().bedrock_runtime.invoke_model(
            modelId=settings.BEDROCK_EMBED_MODEL_ID,
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
    return [float(value) for value in embedding]
