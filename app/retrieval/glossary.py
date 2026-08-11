"""Data-driven terminology expansion for policy retrieval."""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from config import settings
from utils.logging import get_logger

LOGGER = get_logger("app.retrieval.glossary")


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def _matches_trigger(message: str, trigger: str) -> bool:
    normalized_message = _normalize(message)
    normalized_trigger = _normalize(trigger)
    if not normalized_trigger:
        return False
    if len(normalized_trigger) <= 3 and " " not in normalized_trigger:
        return bool(re.search(rf"(?<!\w){re.escape(normalized_trigger)}(?!\w)", normalized_message))
    return normalized_trigger in normalized_message


def _valid_entries(payload: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        return ()
    entries: list[dict[str, Any]] = []
    for entry in payload["entries"]:
        if not isinstance(entry, dict):
            continue
        triggers = entry.get("triggers")
        queries = entry.get("queries")
        if isinstance(triggers, list) and isinstance(queries, list) and triggers and queries:
            entries.append(entry)
    return tuple(entries)


@lru_cache(maxsize=4)
def load_glossary(path: str) -> tuple[dict[str, Any], ...]:
    """Load optional glossary data without making retrieval fail closed."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return _valid_entries(payload)
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        LOGGER.warning("retrieval_glossary_unavailable", path=path, error=str(exc))
        return ()


def glossary_queries(message: str, country: str, language: str) -> list[str]:
    """Return approved terminology queries applicable to the requested locale."""
    if not settings.OPENSEARCH_GLOSSARY_ENABLED:
        return []
    requested_country = (country or "").upper()
    requested_language = (language or "").split("-", 1)[0].lower()
    queries: list[str] = []
    limit = max(0, settings.OPENSEARCH_GLOSSARY_QUERY_LIMIT)
    for entry in load_glossary(settings.OPENSEARCH_GLOSSARY_PATH):
        countries = {str(value).upper() for value in entry.get("country", ["*"])}
        languages = {str(value).split("-", 1)[0].lower() for value in entry.get("language", ["*"])}
        if "*" not in countries and requested_country not in countries:
            continue
        if "*" not in languages and requested_language not in languages:
            continue
        if not any(_matches_trigger(message, str(trigger)) for trigger in entry.get("triggers", [])):
            continue
        for query in entry.get("queries", []):
            cleaned = re.sub(r"\s+", " ", str(query)).strip()
            if cleaned and cleaned not in queries:
                queries.append(cleaned)
            if len(queries) >= limit:
                return queries
    return queries
