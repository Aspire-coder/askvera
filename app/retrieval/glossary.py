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

_MAX_ENTRIES = 500
_MAX_TRIGGERS = 32
_MAX_QUERIES = 16
_MAX_TRIGGER_CHARS = 160
_MAX_QUERY_CHARS = 300
_MAX_HINT_CHARS = 300


def _bounded_strings(value: Any, *, limit: int, max_chars: int) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    result: list[str] = []
    for item in value[:limit]:
        if not isinstance(item, str):
            continue
        cleaned = re.sub(r"\s+", " ", item).strip()
        if cleaned and len(cleaned) <= max_chars and cleaned not in result:
            result.append(cleaned)
    return tuple(result)


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
    for entry in payload["entries"][:_MAX_ENTRIES]:
        if not isinstance(entry, dict):
            continue
        triggers = _bounded_strings(
            entry.get("triggers"), limit=_MAX_TRIGGERS, max_chars=_MAX_TRIGGER_CHARS
        )
        queries = _bounded_strings(
            entry.get("queries"), limit=_MAX_QUERIES, max_chars=_MAX_QUERY_CHARS
        )
        countries = _bounded_strings(entry.get("country", ["*"]), limit=64, max_chars=16)
        languages = _bounded_strings(entry.get("language", ["*"]), limit=64, max_chars=16)
        answer_hint = re.sub(r"\s+", " ", str(entry.get("answer_hint") or "")).strip()
        if len(answer_hint) > _MAX_HINT_CHARS:
            answer_hint = ""
        if triggers and queries and countries and languages:
            entries.append(
                {
                    "country": list(countries),
                    "language": list(languages),
                    "triggers": list(triggers),
                    "queries": list(queries),
                    "answer_hint": answer_hint,
                }
            )
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


def glossary_queries(
    message: str,
    country: str,
    language: str,
    *,
    enabled: bool | None = None,
) -> list[str]:
    """Return approved terminology queries applicable to the requested locale."""
    glossary_enabled = settings.OPENSEARCH_GLOSSARY_ENABLED if enabled is None else enabled
    if not glossary_enabled:
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


def glossary_answer_hints(
    message: str,
    country: str,
    language: str,
    *,
    enabled: bool = False,
) -> list[str]:
    """Return bounded, reviewed terminology facts for the vNext answer prompt."""
    if not enabled:
        return []
    requested_country = (country or "").upper()
    requested_language = (language or "").split("-", 1)[0].lower()
    hints: list[str] = []
    for entry in load_glossary(settings.OPENSEARCH_GLOSSARY_PATH):
        countries = {str(value).upper() for value in entry.get("country", ["*"])}
        languages = {str(value).split("-", 1)[0].lower() for value in entry.get("language", ["*"])}
        if "*" not in countries and requested_country not in countries:
            continue
        if "*" not in languages and requested_language not in languages:
            continue
        if not any(_matches_trigger(message, str(trigger)) for trigger in entry.get("triggers", [])):
            continue
        hint = str(entry.get("answer_hint") or "").strip()
        if hint and hint not in hints:
            hints.append(hint)
    return hints[:4]
