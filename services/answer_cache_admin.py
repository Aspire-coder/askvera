"""Narrow, audited deletion of cached chatbot answers."""

from __future__ import annotations

from datetime import datetime, timezone
import re
import time
from typing import Iterable

import redis

from services.cache import get_cache_client
from services.market_config import get_country_codes, get_widget_country_codes
from utils.logging import get_logger

LOGGER = get_logger("services.answer_cache_admin")

_EXACT_KEY = re.compile(
    r"^ask-vera:(?P<country>[A-Za-z0-9_-]{2,12}):[^:]+:[^:]+:[0-9a-f]{64}$"
)
_SEMANTIC_KEY = re.compile(
    r"^ask-vera:semantic:(?P<country>[a-z0-9_-]{2,12}):[^:]+:[^:]+:"
    r"[0-9a-f]{20}(?::entry:[0-9a-f]{64})?$"
)
_DELETE_BATCH_SIZE = 250


class AnswerCacheUnavailable(RuntimeError):
    """Raised when the answer cache cannot be safely reset."""


def _matches_scope(
    key: str,
    country: str,
    include_semantic: bool,
    allowed_countries: set[str],
) -> str | None:
    exact_match = _EXACT_KEY.fullmatch(key)
    exact_country = exact_match.group("country").upper() if exact_match else ""
    if exact_match and exact_country in allowed_countries and (
        country == "ALL" or exact_match.group("country").upper() == country
    ):
        return "exact"
    if include_semantic:
        semantic_match = _SEMANTIC_KEY.fullmatch(key)
        semantic_country = (
            semantic_match.group("country").upper() if semantic_match else ""
        )
        if semantic_match and semantic_country in allowed_countries and (
            country == "ALL" or semantic_match.group("country").upper() == country
        ):
            return "semantic"
    return None


def _delete_batches(client: redis.Redis, keys: Iterable[str]) -> int:
    key_list = list(dict.fromkeys(keys))
    deleted = 0
    for index in range(0, len(key_list), _DELETE_BATCH_SIZE):
        deleted += int(client.unlink(*key_list[index : index + _DELETE_BATCH_SIZE]))
    return deleted


def reset_answer_cache(
    country: str,
    *,
    include_semantic: bool,
    correlation_id: str,
) -> dict[str, object]:
    """Delete only exact and optional semantic answer keys for one market or all markets."""
    client = get_cache_client()
    if client is None:
        raise AnswerCacheUnavailable("The answer cache is not configured.")

    normalized = country.strip().upper()
    allowed_countries = get_country_codes() | get_widget_country_codes()
    if normalized != "ALL" and normalized not in allowed_countries:
        raise ValueError("Unsupported answer-cache country.")
    started = time.monotonic()
    exact_keys: list[str] = []
    semantic_keys: list[str] = []
    try:
        scan_patterns = ["ask-vera:*"] if normalized == "ALL" else [
            f"ask-vera:{normalized}:*",
            *([f"ask-vera:semantic:{normalized.lower()}:*"] if include_semantic else []),
        ]
        for pattern in scan_patterns:
            for raw_key in client.scan_iter(match=pattern, count=500):
                key = raw_key.decode("utf-8") if isinstance(raw_key, bytes) else str(raw_key)
                cache_type = _matches_scope(
                    key, normalized, include_semantic, allowed_countries
                )
                if cache_type == "exact":
                    exact_keys.append(key)
                elif cache_type == "semantic":
                    semantic_keys.append(key)

        exact_deleted = _delete_batches(client, exact_keys)
        semantic_deleted = _delete_batches(client, semantic_keys)
    except redis.RedisError as exc:
        LOGGER.exception(
            "answer_cache_reset_failed",
            correlation_id=correlation_id,
            country=normalized,
        )
        raise AnswerCacheUnavailable("The answer cache could not be reset.") from exc

    result: dict[str, object] = {
        "country": normalized,
        "mode": "exact_and_semantic" if include_semantic else "exact",
        "exact_deleted": exact_deleted,
        "semantic_deleted": semantic_deleted,
        "total_deleted": exact_deleted + semantic_deleted,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }
    LOGGER.warning("answer_cache_reset", correlation_id=correlation_id, **result)
    return result
