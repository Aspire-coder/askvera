"""Active knowledge-generation lookup for atomic document publication."""

from __future__ import annotations

import re
import threading
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from services.db import get_engine
from utils.logging import get_logger

LOGGER = get_logger("services.knowledge_generations")

_CACHE_SECONDS = 15.0
_cache_lock = threading.Lock()
_cache_loaded_at = 0.0
_cache_rows: list[dict[str, Any]] = []
# Per-request outcome of the lookup, for retrieval diagnostics only. It holds the
# exception *type name* of a failed lookup and never its message or traceback,
# which carry the database host, port and SQL text.
_lookup_failure: ContextVar[str | None] = ContextVar("askvera_generation_lookup_failure", default=None)


def reset_generation_lookup_failure() -> None:
    """Start a new request's lookup outcome, and allow its one failure warning."""
    _lookup_failure.set(None)


def generation_lookup_failure() -> str | None:
    """Return the exception type name of this request's failed lookup, if any."""
    return _lookup_failure.get()


def build_logical_document_id(
    *,
    logical_document_id: str,
    country: str,
    language: str,
    document_type: str,
    access_scope: str,
    source_file: str,
) -> str:
    """Build the stable, locale-namespaced replacement slot for a document."""
    requested_id = logical_document_id or Path(source_file).stem
    normalized_id = re.sub(r"[^a-z0-9]+", "-", requested_id.lower()).strip("-")
    return ":".join(
        (
            access_scope.lower(),
            country.upper(),
            language.lower(),
            document_type.lower(),
            normalized_id[:96] or "document",
        )
    )


def clear_active_generation_cache() -> None:
    """Force the next lookup to reload publication pointers from the database."""
    global _cache_loaded_at, _cache_rows
    with _cache_lock:
        _cache_loaded_at = 0.0
        _cache_rows = []


def active_generation_ids(
    *,
    countries: set[str],
    languages: set[str],
    access_scope: str,
    document_type: str = "",
) -> set[str]:
    """Return active ingestion IDs for an allowed locale and scope."""
    normalized_countries = {value.upper() for value in countries if value}
    normalized_languages = {value.lower() for value in languages if value}
    result: set[str] = set()
    for row in _active_generation_rows():
        if row["access_scope"] != access_scope:
            continue
        if document_type and row["document_type"] != document_type:
            continue
        if access_scope != "global" and row["country"].upper() not in normalized_countries:
            continue
        if normalized_languages and row["language"].lower() not in normalized_languages:
            continue
        ingestion_id = str(row["active_ingestion_id"] or "")
        if ingestion_id:
            result.add(ingestion_id)
    return result


def _active_generation_rows(*, fresh: bool = False) -> list[dict[str, Any]]:
    global _cache_loaded_at, _cache_rows
    now = time.monotonic()
    with _cache_lock:
        if not fresh and _cache_rows and now - _cache_loaded_at < _CACHE_SECONDS:
            return list(_cache_rows)
        try:
            with get_engine().connect() as connection:
                rows = connection.execute(
                    text(
                        """
                        SELECT country, language, document_type, access_scope,
                               active_ingestion_id
                        FROM knowledge_active_generations
                        WHERE active_ingestion_id <> ''
                        """
                    )
                ).mappings().all()
        except SQLAlchemyError as exc:
            # Still fails closed with no rows. Log once per request, with the
            # exception type name only: no traceback, message, host or SQL.
            error_type = type(exc).__name__
            if _lookup_failure.get() is None:
                LOGGER.error("active_generation_lookup_failed", error_type=error_type)
            _lookup_failure.set(error_type)
            return []
        _cache_rows = [dict(row) for row in rows]
        _cache_loaded_at = now
        return list(_cache_rows)
