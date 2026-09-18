"""OpenSearch-backed section retrieval."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from contextvars import ContextVar, Token
from functools import lru_cache
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection
from opensearchpy.exceptions import (
    AuthenticationException,
    AuthorizationException,
    ConnectionError,
    ConflictError,
    NotFoundError,
    RequestError,
    TransportError,
)

from config import settings
from services.aws_clients import get_aws_clients
from services.embeddings import embed_text
from services.guardrails import is_policy_safety_question
from services.knowledge_generations import (
    active_generation_ids,
    generation_lookup_failure,
    reset_generation_lookup_failure,
)
from services.market_config import (
    find_market_mentions,
    find_shared_office_record_countries,
    find_sponsoring_directory_alias_matches,
    get_document_country_codes,
    load_global_directory_markets,
    load_market_config,
    superseded_market_codes_for_alias_term,
)
from utils.logging import get_logger
from utils.opensearch_fields import exact_term_query, exact_terms_query

from .models import RetrievedDocument, RetrievalAvailability, RetrievalResult
from .providers import (
    DIRECTORY_OPERATIONAL_QUESTION_RE,
    DIRECTORY_POLICY_WORDING_RE,
    OWN_MARKET_DIRECTORY_FIELD_RE,
    RetrievalQueryPlan,
    _document_relevance,
    _planned_retrieval_plan,
    _tokens,
)
from utils.directory_fields import parse_directory_fields
from .section_index import _character_overlap, _confidence_from_documents, _source_score
from .typo_safety import safe_typo_ranking_queries

LOGGER = get_logger("app.retrieval.opensearch_sections")

GLOBAL_DIRECTORY_DOCUMENT_TYPES = (
    "office_directory",
    "international_sponsoring_directory",
)
_SHARD_CONFIGURATION_FAILURE_TYPES = frozenset({
    "authentication_exception",
    "authorization_exception",
    "illegal_argument_exception",
    "index_not_found_exception",
    "mapper_parsing_exception",
    "parsing_exception",
    "query_shard_exception",
    "resource_not_found_exception",
    "security_exception",
    "validation_exception",
})
_TRANSIENT_SHARD_FAILURE_TYPES = frozenset({
    "circuit_breaking_exception",
    "cluster_block_exception",
    "es_rejected_execution_exception",
    "node_not_connected_exception",
    "process_cluster_event_timeout_exception",
    "unavailable_shards_exception",
})
_DIRECTORY_DETAIL_RE = re.compile(
    r"\b(?:address|business\s+hours?|email|office|phone|telephone|website|contact)\b",
    re.IGNORECASE,
)
_GLOBAL_DIRECTORY_INTENT_RE = re.compile(
    r"\b(?:international\s+)?sponsoring\b|" + _DIRECTORY_DETAIL_RE.pattern,
    re.IGNORECASE,
)


def _normalize_text(value: str) -> str:
    """Normalize text for glossary trigger checks."""
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    return " ".join("".join(character if character.isalnum() else " " for character in normalized).split())


def _search_hits(response: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return OpenSearch hits, or no hits when one optional channel failed."""
    if response is None:
        return []
    return response.get("hits", {}).get("hits", [])


def _weighted_search_hits(response: dict[str, Any] | None, weight: float) -> list[dict[str, Any]]:
    """Return one channel's hits with its planned query weight applied."""
    return [
        {**hit, "_score": float(hit.get("_score") or 0.0) * weight}
        for hit in _search_hits(response)
    ]


@lru_cache(maxsize=1)
def _client() -> OpenSearch:
    """Return an IAM-signed OpenSearch client."""
    if not settings.OPENSEARCH_ENDPOINT:
        raise RuntimeError("OPENSEARCH_ENDPOINT is required for opensearch_section retrieval.")
    credentials = boto3.Session().get_credentials()
    if credentials is None:
        raise RuntimeError("AWS credentials are required for OpenSearch retrieval.")
    auth = AWSV4SignerAuth(credentials, settings.AWS_REGION, settings.OPENSEARCH_SERVICE)
    endpoint = settings.OPENSEARCH_ENDPOINT.replace("https://", "").rstrip("/")
    return OpenSearch(
        hosts=[{"host": endpoint, "port": 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=settings.AWS_READ_TIMEOUT_SECONDS,
        max_retries=settings.AWS_MAX_ATTEMPTS,
        retry_on_timeout=True,
    )


def _language_filter(language: str) -> dict[str, Any]:
    """Filter to the requested language, with an explicit optional English fallback."""
    normalized = (language or "en").split("-", 1)[0].lower()
    if normalized == "en":
        return {"term": {"language": "en"}}
    languages = [normalized]
    if settings.OPENSEARCH_ALLOW_ENGLISH_FALLBACK:
        languages.append("en")
    return {"terms": {"language": languages}}


def _language_key(language: str) -> str:
    """Use one locale convention for documents and content-managed glossary entries."""
    return (language or "en").split("-", 1)[0].lower()


def _scope_filter(country: str, language: str, scope: str) -> dict[str, Any]:
    """Build an isolated locale or global-document filter."""
    if scope == "global":
        return {
            "bool": {
                "filter": [
                    {"term": {"access_scope": "global"}},
                    _language_filter(language),
                ]
            }
        }
    return {
        "bool": {
            "filter": [
                {"terms": {"country": sorted(get_document_country_codes(country))}},
                _language_filter(language),
            ]
        }
    }


# Per-request count of generation filters built, and how many fell back to the
# no-generation sentinel. Reset when retrieval starts; read into its metadata.
_generation_filter_counts: ContextVar[tuple[int, int]] = ContextVar(
    "askvera_generation_filter_counts", default=(0, 0)
)


def _start_generation_lookup_signal() -> None:
    reset_generation_lookup_failure()
    _generation_filter_counts.set((0, 0))


def _count_generation_filter(*, sentinel: bool) -> None:
    total, sentinels = _generation_filter_counts.get()
    _generation_filter_counts.set((total + 1, sentinels + int(sentinel)))


def _generation_lookup_fields() -> dict[str, Any]:
    """Say why a generation-filtered search may be empty; internal diagnostics only.

    ``failed``: a lookup raised; ``error_type`` is the exception type name only.
    ``none_active``: no failure, and every filter fell back to the sentinel.
    ``ok``: no failure, and at least one filter used published generation ids.
    Absent when the generation pointer is off or no filter was built.
    """
    total, sentinels = _generation_filter_counts.get()
    if total == 0:
        return {}
    error_type = generation_lookup_failure()
    if error_type:
        status = "failed"
    elif sentinels == total:
        status = "none_active"
    else:
        status = "ok"
    return {
        "generation_lookup": {
            "status": status,
            "error_type": error_type,
            "filter_count": total,
            "sentinel_filter_count": sentinels,
        }
    }


# Rank-list capture, for offline rank-fusion and selector diagnosis: each
# search's ranked hits with raw scores, the merged order, the candidates sent to
# the selector and the selector's raw picks. Diagnostic only and off by default:
# the orchestrator's benchmark diagnostic capture is the only caller of
# enable_rank_list_capture, for one request. When off, every hook below returns
# at once and retrieval adds no metadata key. It never reads settings or the
# environment, records no document or query text, and never mutates a hit or row.
RANK_LIST_CAPTURE_VERSION = 1
RANK_LIST_METADATA_KEYS = (
    "retrieval_rank_lists",
    "candidate_section_ids",
    "evidence_selector_candidate_section_ids",
    "evidence_selector_selected_ranks",
)
_RANK_LIST_DOCUMENT_FIELDS = (
    "id", "section_id", "parent_section_id", "country", "language",
    "access_scope", "document_type", "chunk_type",
)
_RANK_LIST_MAX_SEARCHES = 24
_RANK_LIST_MAX_HITS = 30
_RANK_LIST_MAX_MERGED = 60
_RANK_LIST_MAX_RANKS = 30
_RANK_LIST_MAX_TARGETS = 16
_RANK_LIST_ID_CHARS = 160
_RANK_LIST_SECTION_CHARS = 48
_RANK_LIST_CODE_CHARS = 24
_rank_list_capture_enabled: ContextVar[bool] = ContextVar("askvera_rank_list_capture", default=False)
_rank_list_record: ContextVar[dict[str, Any] | None] = ContextVar("askvera_rank_list_record", default=None)
_rank_list_context_resolution: ContextVar[dict[str, str] | None] = ContextVar(
    "askvera_rank_list_context_resolution", default=None
)


def enable_rank_list_capture() -> Token[bool]:
    """Turn rank-list capture on in the current context; reset with the returned token."""
    return _rank_list_capture_enabled.set(True)


def disable_rank_list_capture(token: Token[bool]) -> None:
    _rank_list_capture_enabled.reset(token)


def set_rank_list_context_resolution(value: dict[str, str] | None) -> Token[dict[str, str] | None]:
    """Attach orchestrator-resolved follow-up provenance to this request only."""
    return _rank_list_context_resolution.set(dict(value) if value is not None else None)


def reset_rank_list_context_resolution(token: Token[dict[str, str] | None]) -> None:
    """Reset one request's follow-up provenance context."""
    _rank_list_context_resolution.reset(token)


def _start_rank_list_record() -> dict[str, Any] | None:
    if not _rank_list_capture_enabled.get():
        return None
    record: dict[str, Any] = {
        "version": RANK_LIST_CAPTURE_VERSION,
        "hit_fields": ["section_id", "rank", "raw_score", "document"],
        "document_fields": list(_RANK_LIST_DOCUMENT_FIELDS),
        "limits": {
            "searches": _RANK_LIST_MAX_SEARCHES,
            "hits_per_search": _RANK_LIST_MAX_HITS,
            "merged": _RANK_LIST_MAX_MERGED,
        },
        "documents": [],
        "searches": [],
        "searches_not_recorded": 0,
        "merged_count": None,
        "merged_order": None,
        "selector_outcome": "not_called",
        "selector_candidates": None,
        "selector_relevant_evidence": None,
        "selector_selected_ranks": None,
        "runtime_scope_intent": None,
        "authorized_policy_market": None,
        "context_resolution": _rank_list_context_resolution.get(),
        "recording_errors": 0,
        "_document_index": {},
        "_selector_candidate_section_ids": None,
    }
    _rank_list_record.set(record)
    return record


def _rank_list_text(value: object, limit: int) -> str:
    return str(value or "")[:limit]


def _rank_list_document(record: dict[str, Any], identifier: object, fields: dict[str, Any]) -> int | None:
    """Return the document-table index for one hit or row; ``None`` when it has no id."""
    key = _rank_list_text(identifier, _RANK_LIST_ID_CHARS)
    if not key:
        return None
    index = record["_document_index"]
    if key not in index:
        index[key] = len(record["documents"])
        record["documents"].append([
            key,
            _rank_list_text(fields.get("section_id"), _RANK_LIST_SECTION_CHARS),
            _rank_list_text(fields.get("parent_section_id"), _RANK_LIST_SECTION_CHARS),
            *(_rank_list_text(fields.get(name), _RANK_LIST_CODE_CHARS) for name in _RANK_LIST_DOCUMENT_FIELDS[3:]),
        ])
    return index[key]


def _record_rank_list_search(
    record: dict[str, Any] | None,
    kind: str,
    query_index: int | None,
    weight: float,
    response: dict[str, Any],
) -> None:
    """Record one search's ranked hits with the raw OpenSearch score, before any weighting."""
    if record is None:
        return
    try:
        if len(record["searches"]) >= _RANK_LIST_MAX_SEARCHES:
            record["searches_not_recorded"] += 1
            return
        hits = response.get("hits", {}).get("hits", [])
        ranked = []
        for rank, hit in enumerate(hits[:_RANK_LIST_MAX_HITS], start=1):
            source = hit.get("_source", {}) or {}
            ranked.append([
                _rank_list_text(source.get("section_id"), _RANK_LIST_SECTION_CHARS),
                rank,
                float(hit.get("_score") or 0.0),
                _rank_list_document(record, source.get("id") or hit.get("_id", ""), source),
            ])
        record["searches"].append(
            {"kind": kind, "query_index": query_index, "weight": weight, "hit_count": len(hits), "hits": ranked}
        )
    except Exception:  # noqa: BLE001 - diagnostic recording must never change retrieval
        record["recording_errors"] += 1


def _record_rank_list_merged(record: dict[str, Any] | None, rows: list[tuple[dict[str, Any], float]]) -> None:
    if record is None:
        return
    try:
        record["merged_count"] = len(rows)
        record["merged_order"] = [
            [
                _rank_list_text(row.get("section_id"), _RANK_LIST_SECTION_CHARS),
                float(score),
                _rank_list_document(record, row.get("id"), row),
            ]
            for row, score in rows[:_RANK_LIST_MAX_MERGED]
        ]
    except Exception:  # noqa: BLE001 - diagnostic recording must never change retrieval
        record["recording_errors"] += 1


def _record_rank_list_selector(
    outcome: str,
    *,
    candidates: list[tuple[dict[str, Any], float]] | None = None,
    ranks: list[int] | None = None,
    relevant_evidence: bool | None = None,
) -> None:
    """Record what the selector was shown and its raw ranked picks, before binding."""
    record = _rank_list_record.get() if _rank_list_capture_enabled.get() else None
    if record is None:
        return
    try:
        record["selector_outcome"] = outcome
        if candidates is not None:
            record["selector_candidates"] = [_rank_list_document(record, row.get("id"), row) for row, _score in candidates]
            record["_selector_candidate_section_ids"] = [
                _rank_list_text(row.get("section_id"), _RANK_LIST_SECTION_CHARS) for row, _score in candidates
            ]
        if ranks is not None:
            record["selector_selected_ranks"] = [int(rank) for rank in ranks[:_RANK_LIST_MAX_RANKS]]
            record["selector_relevant_evidence"] = relevant_evidence
    except Exception:  # noqa: BLE001 - diagnostic recording must never change retrieval
        record["recording_errors"] += 1


def _rank_list_fields(
    record: dict[str, Any] | None,
    *,
    raw_rows: list[tuple[dict[str, Any], float]] | None = None,
    search_plan: RetrievalQueryPlan | None = None,
    target_country_names: set[str] | None = None,
) -> dict[str, Any]:
    """Close this retrieval's record and return its metadata keys; ``{}`` when capture is off."""
    if record is None:
        return {}
    _rank_list_record.set(None)
    try:
        if search_plan is not None:
            record["query_count"] = len(search_plan.queries)
            record["prefer_outline"] = bool(search_plan.prefer_outline)
            record["include_global_documents"] = bool(search_plan.include_global_documents)
            record["runtime_scope_intent"] = search_plan.runtime_scope_intent
            record["authorized_policy_market"] = search_plan.authorized_policy_market
        if target_country_names is not None:
            record["target_country_names"] = sorted(
                _rank_list_text(name, _RANK_LIST_SECTION_CHARS) for name in target_country_names
            )[:_RANK_LIST_MAX_TARGETS]
        selector_section_ids = record["_selector_candidate_section_ids"]
        fields: dict[str, Any] = {
            # A JSON copy: plain types only, and detached from the closed record.
            "retrieval_rank_lists": json.loads(
                json.dumps({key: value for key, value in record.items() if not key.startswith("_")})
            ),
            "evidence_selector_candidate_section_ids": (
                list(selector_section_ids) if selector_section_ids is not None else None
            ),
            "evidence_selector_selected_ranks": (
                list(record["selector_selected_ranks"]) if record["selector_selected_ranks"] is not None else None
            ),
        }
        if raw_rows is not None:
            # Each candidate's own section id, parallel to candidate_sources,
            # whose "section" prefers the parent.
            fields["candidate_section_ids"] = [
                _rank_list_text(row.get("section_id"), _RANK_LIST_SECTION_CHARS)
                for row, _score in raw_rows[: settings.OPENSEARCH_CANDIDATE_COUNT]
            ]
        return fields
    except Exception:  # noqa: BLE001 - diagnostic recording must never change retrieval
        return {"retrieval_rank_lists": {"version": RANK_LIST_CAPTURE_VERSION, "recording_failed": True}}


def _generation_filters(
    country: str,
    language: str,
    scope: str,
    *,
    document_type: str = "",
) -> list[dict[str, Any]]:
    """Restrict retrieval to atomically published generations when enabled."""
    if not settings.ADMIN_INGESTION_GENERATION_POINTER_ENABLED:
        return []
    access_scope = "global" if scope == "global" else "country"
    normalized_language = _language_key(language)
    languages: set[str] = set()
    if access_scope != "global":
        languages.add(normalized_language)
        if settings.OPENSEARCH_ALLOW_ENGLISH_FALLBACK and normalized_language != "en":
            languages.add("en")
    countries = (
        set(get_document_country_codes(country))
        if access_scope != "global"
        else set()
    )
    generation_ids = active_generation_ids(
        countries=countries,
        languages=languages,
        access_scope=access_scope,
        document_type=document_type,
    )
    _count_generation_filter(sentinel=not generation_ids)
    if not generation_ids:
        return [exact_term_query("ingestion_id", "__no_active_generation__")]
    return [exact_terms_query("ingestion_id", sorted(generation_ids))]


def is_approved_source(uri: str, country: str, language: str, correlation_id: str = "system") -> bool:
    """Confirm that a citation source is active and available to the requested locale."""
    normalized_language = _language_key(language)
    allowed_languages = [normalized_language]
    if settings.OPENSEARCH_ALLOW_ENGLISH_FALLBACK and normalized_language != "en":
        allowed_languages.append("en")
    country_codes = sorted(get_document_country_codes(country))
    query = {
        "size": 5,
        "_source": ["source_uri", "country", "language", "access_scope", "status"],
        "query": {
            "bool": {
                "filter": [
                    {"term": {"source_uri": uri}},
                    {"term": {"status": "active"}},
                ],
                "should": [
                    {
                        "bool": {
                            "filter": [
                                {"term": {"access_scope": "global"}},
                                *_generation_filters("", language, "global"),
                            ]
                        }
                    },
                    {
                        "bool": {
                            "filter": [
                                {"term": {"access_scope": "country"}},
                                {"terms": {"country": country_codes}},
                                {"terms": {"language": allowed_languages}},
                                *_generation_filters(country, language, "country"),
                            ]
                        }
                    },
                ],
                "minimum_should_match": 1,
            }
        },
    }
    try:
        response = _client().search(index=settings.OPENSEARCH_INDEX, body=query)
    except Exception:
        LOGGER.exception(
            "source_authorization_failed",
            correlation_id=correlation_id,
            source_uri=uri,
        )
        return False

    for hit in response.get("hits", {}).get("hits", []):
        source = hit.get("_source", {})
        if source.get("source_uri") != uri or source.get("status") != "active":
            continue
        if source.get("access_scope") == "global":
            return True
        if (
            str(source.get("country") or "").upper() in country_codes
            and _language_key(str(source.get("language") or "")) in allowed_languages
        ):
            return True
    return False


def _text_query(message: str, country: str, language: str, *, scope: str = "locale") -> dict[str, Any]:
    """Build a metadata-filtered BM25 query."""
    return {
        "size": settings.OPENSEARCH_CANDIDATE_COUNT,
        "query": {
            "bool": {
                "filter": [
                    _scope_filter(country, language, scope),
                    {"term": {"status": "active"}},
                    *_generation_filters(country, language, scope),
                ],
                "should": [
                    {
                        "multi_match": {
                            "query": message,
                            "fields": [
                                "section_id^8",
                                "section_title^6",
                                "content^3",
                                "search_text",
                            ],
                            "type": "best_fields",
                            "operator": "or",
                            "fuzziness": "AUTO",
                        }
                    },
                    {"match_phrase": {"section_title": {"query": message, "boost": 5}}},
                    {"match_phrase": {"content": {"query": message, "boost": 2}}},
                ],
                "minimum_should_match": 1,
            }
        },
    }


_SECTION_REFERENCE_RE = re.compile(
    r"(?:\b(?:section|sec\.?)\s*|§\s*)([0-9]+(?:[.-][0-9]+)*(?:[.-]?[a-z])?)\b",
    re.IGNORECASE,
)


def _normalize_section_reference(value: str) -> str:
    """Normalize common human-written section references to the indexed form."""
    normalized = re.sub(r"\s+", "", value).replace("-", ".").lower()
    return normalized.rstrip(".")


def _section_reference(message: str) -> str | None:
    """Extract an explicit policy section reference without guessing from prose."""
    match = _SECTION_REFERENCE_RE.search(message or "")
    return _normalize_section_reference(match.group(1)) if match else None


def _exact_section_query(section_id: str, country: str, language: str) -> dict[str, Any]:
    """Build a locale-isolated exact section lookup for explicit references only."""
    return {
        "size": settings.OPENSEARCH_CANDIDATE_COUNT,
        "query": {
            "bool": {
                "filter": [
                    _scope_filter(country, language, "locale"),
                    {"term": {"status": "active"}},
                    *_generation_filters(country, language, "locale"),
                    exact_term_query("section_id", section_id),
                ],
            }
        },
    }


def _directory_text_query(
    message: str,
    target_country_names: set[str] | None = None,
) -> dict[str, Any]:
    """Build a metadata-aware query for globally available directory records."""
    should_queries: list[dict[str, Any]] = [
        {
            "multi_match": {
                "query": message,
                "fields": [
                    "metadata.record_country^12",
                    "section_title^10",
                    "content^4",
                    "search_text^2",
                ],
                "type": "best_fields",
                "operator": "or",
                "fuzziness": "AUTO",
            }
        },
        {"match_phrase": {"metadata.record_country": {"query": message, "boost": 18}}},
        {"match_phrase": {"section_title": {"query": message, "boost": 8}}},
    ]
    for name in sorted(target_country_names or set()):
        should_queries.append(
            {"match_phrase": {"metadata.record_country": {"query": name, "boost": 40}}}
        )
    filters: list[dict[str, Any]] = [
        _scope_filter("", "", "global"),
        {"term": {"status": "active"}},
        {"terms": {"document_type": list(GLOBAL_DIRECTORY_DOCUMENT_TYPES)}},
        *_generation_filters("", "en", "global"),
    ]
    country_filter = _record_country_filter(target_country_names or set())
    if country_filter is not None:
        filters.append(country_filter)
    return {
        "size": settings.OPENSEARCH_CANDIDATE_COUNT,
        "query": {
            "bool": {
                "filter": filters,
                "should": should_queries,
                "minimum_should_match": 1,
            }
        },
    }


def _outline_text_query(message: str, country: str, language: str) -> dict[str, Any]:
    """Search document outlines without letting repeated body text crowd them out."""
    query = _text_query(message, country, language, scope="locale")
    query["query"]["bool"]["filter"].append({"term": {"chunk_type": "document_outline"}})
    return query


def _directory_record_country_score(
    message: str,
    row: dict[str, Any],
    target_country_names: set[str] | None = None,
) -> float:
    """Reward directory records whose own country metadata matches the query."""
    if row.get("document_type") not in GLOBAL_DIRECTORY_DOCUMENT_TYPES:
        return 0.0
    metadata = dict(row.get("metadata") or {})
    record_country = _normalize_text(str(metadata.get("record_country") or ""))
    normalized_message = _normalize_text(message)
    if not record_country or not normalized_message:
        return 0.0
    if target_country_names:
        normalized_targets = {_normalize_text(name) for name in target_country_names}
        # "Kenya/East Africa" names its market before the "/". Compared whole,
        # "kenya east africa" matched no target, so the Kenya record took the
        # wrong-country penalty below and was filtered out even when the
        # selector chose it (live demo run). Only "/"-separated parts count, so
        # "Guinea" still never matches "Equatorial Guinea".
        record_segments = {
            _normalize_text(part) for part in str(metadata.get("record_country") or "").split("/") if part.strip()
        }
        if record_country in normalized_targets or record_segments & normalized_targets:
            return 8.0
        # A country explicitly named in the question outranks the selected
        # widget market. This matters for global-directory questions such as
        # "What is Gambia's telephone number?" asked from a US widget.
        if record_country in normalized_message:
            return 6.0
        return -4.0
    if record_country in normalized_message:
        return 2.4

    message_tokens = set(normalized_message.split())
    country_tokens = record_country.split()
    acronym = "".join(token[0] for token in country_tokens if token)
    if len(acronym) >= 2 and acronym in message_tokens:
        return 2.2

    compact_country = "".join(country_tokens)
    compact_message_tokens = [token for token in message_tokens if len(token) >= 4]
    if any(_character_overlap(token, compact_country) >= 0.72 for token in compact_message_tokens):
        return 1.6
    return 0.0


# --- Deterministic post-selector dominance guard -----------------------
#
# 2026-09-14: two production deploy-canary runs, hours apart, both failed the
# same case (kyrgyzstan-foreign-fbo-bonus-release-gate) with IDENTICAL scores
# (document_scores [0.95, 1.066, 1.09, 9.444, 4.37]), the LLM evidence
# selector reordering a dominant, country-matched global directory record
# (score 9.444) behind an unrelated, low-scoring US policy section. The
# 2026-09-07 audit (docs/audits/2026-09-07/SELECTOR_DEMOTES_MATCHING_DIRECTORY_RECORD.md)
# had attributed this to LLM sampling and "fixed" it with
# BEDROCK_CLASSIFIER_TEMPERATURE=0; tonight's evidence shows that only made
# the wrong pick deterministic instead of intermittent. This guard restores
# the pre-selector order in exactly that shape, without touching the
# selector's prompt, its model call, or either scoring function.
#
# Fires only when ALL of:
#   1. The question itself is asking for directory/contact/logistics detail
#      content (`_directory_guard_topic_match`) - not merely a general
#      "policy" or "sponsoring rules" question that happens to name a
#      country. Review finding (2026-09-14): a named foreign country alone
#      reliably earns +8.0 from `_directory_record_country_score`, which can
#      produce >2x dominance even for "What is the company policy on
#      sponsoring someone in Italy?" (an Austrian session) - a case where
#      `tests/unit/test_mixed_sponsoring_policy_scope.py` pins that the
#      session's OWN policy must stay first. This gate keeps the guard from
#      ever firing on that shape of question.
#   2. The single highest-scoring row in raw_rows (the candidates *before*
#      the LLM selector reorders them) is a global directory row
#      (GLOBAL_DIRECTORY_DOCUMENT_TYPES).
#   3. That row's score reflects a genuine target-country match from
#      `_directory_record_country_score` - the >= 6.0 branch that only
#      awards points when `target_country_names` was supplied (a country was
#      actually named/targeted) and it matched the record's own country
#      metadata or the question text - never the generic acronym/lexical
#      fallback branch (0.0-2.4) that runs when no country was targeted at
#      all. This keeps the guard from ever firing on a directory row that
#      merely scored well for unrelated reasons.
#   4. Its score dominates the best-of-the-rest raw candidate by a wide,
#      deliberately conservative margin. Calibration, from real numbers: the
#      Kyrgyzstan failure showed 9.444 vs next-best 4.37 (ratio ~2.16x); the
#      canary fixture's other directory-should-win cases (Uruguay, Belgium,
#      Thailand, Algeria, New Zealand) all describe the same shape,
#      a dominant record around 9-13 against ~1-4.7 for everything else.
#      The thresholds below (ratio >= 2.0, absolute score >= 7.0) sit safely
#      under that real signal - comfortably wide enough to catch genuine
#      routs like this one, while nowhere near a normal close contest
#      (ratio near 1) that the selector is legitimately allowed to resolve.
#      "Highest-scoring" and "best-of-the-rest" are derived by score, not by
#      list position: an optional Bedrock reranker (`rerank_rows`) can already
#      have reordered `raw_rows` by semantic rank without changing scores, so
#      index 0/1 are not reliably the top two.
#   5. The selector's reordered `rows` does not already have that same row
#      first - i.e. it actually got demoted.
#
# When it fires, the guard moves that one row back to the front of `rows`,
# leaving every other candidate's relative order untouched.
#
# It never operates on an empty selector result: when hardening is on and the
# selector deliberately returns `[]` (a considered "no relevant evidence"
# refusal), that refusal must stay a refusal, never be turned into an answer
# by resurrecting a raw candidate the selector never endorsed.
_DIRECTORY_DOMINANCE_MIN_RATIO = 2.0
_DIRECTORY_DOMINANCE_MIN_SCORE = 7.0
_DIRECTORY_DOMINANCE_MIN_COUNTRY_BONUS = 6.0

# Topical gate for the guard above: true only for a question actually asking
# for directory/contact/logistics detail content. Built from the narrowest
# existing "wants directory detail" signals in this codebase -
# `_DIRECTORY_DETAIL_RE` (address/hours/email/office/phone/website/contact)
# and `DIRECTORY_OPERATIONAL_QUESTION_RE` (imported from providers.py: minimum
# order, delivery cost, lead time, payment methods, business hours, phone) -
# plus "bonus", the Kyrgyzstan bug case's own wording ("How are foreign FBOs
# paid their bonus in Kyrgyzstan?") and the same operational class as
# `tests/fixtures/benchmark_cases.json`'s "Can a foreign FBO receive bonuses
# from Forever Algeria?". A question using policy/rules wording
# (`DIRECTORY_POLICY_WORDING_RE`) never matches, even when it also contains
# one of these words, so "company policy on sponsoring" and "sponsoring
# rules" keep resolving through the selector, never this guard.
_DIRECTORY_GUARD_TOPIC_RE = re.compile(
    _DIRECTORY_DETAIL_RE.pattern + r"|" + DIRECTORY_OPERATIONAL_QUESTION_RE.pattern + r"|\bbonus(?:es)?\b",
    re.IGNORECASE,
)


def _directory_guard_topic_match(message: str) -> bool:
    """True when the question wants directory/contact/logistics detail
    content rather than a general policy/rules question naming a country."""
    text = message or ""
    if DIRECTORY_POLICY_WORDING_RE.search(text):
        return False
    return bool(_DIRECTORY_GUARD_TOPIC_RE.search(text))


def _dominant_directory_row(
    message: str,
    raw_rows: list[tuple[dict[str, Any], float]],
    target_country_names: set[str] | None,
) -> tuple[dict[str, Any], float] | None:
    """Return the top-scoring raw candidate if it is a decisively dominant,
    country-matched global directory record answering a directory-detail
    question; otherwise None. See the guard documentation above for the exact
    thresholds and how they were calibrated."""
    if not raw_rows:
        return None
    if not _directory_guard_topic_match(message):
        return None
    top_index, (top_row, top_score) = max(
        enumerate(raw_rows), key=lambda indexed: indexed[1][1]
    )
    if top_row.get("document_type") not in GLOBAL_DIRECTORY_DOCUMENT_TYPES:
        return None
    if top_score < _DIRECTORY_DOMINANCE_MIN_SCORE:
        return None
    country_bonus = _directory_record_country_score(message, top_row, target_country_names)
    if country_bonus < _DIRECTORY_DOMINANCE_MIN_COUNTRY_BONUS:
        return None
    rest_scores = [score for index, (_row, score) in enumerate(raw_rows) if index != top_index]
    next_score = max(rest_scores, default=0.0)
    if next_score > 0 and (top_score / next_score) < _DIRECTORY_DOMINANCE_MIN_RATIO:
        return None
    return top_row, top_score


def _restore_dominant_directory_record(
    message: str,
    raw_rows: list[tuple[dict[str, Any], float]],
    rows: list[tuple[dict[str, Any], float]],
    target_country_names: set[str] | None,
) -> list[tuple[dict[str, Any], float]]:
    """Deterministically undo the selector demoting a dominant directory row.

    Runs after `_select_evidence_rows` has reordered candidates. If the
    single highest-scoring raw candidate is a decisively dominant,
    country-matched global directory record answering a directory-detail
    question (`_dominant_directory_row`) and the selector's output does not
    already have it first, move it back to the front, leaving everything else
    in the selector's chosen order. Does nothing when there is no such row,
    it is already on top, or the selector deliberately returned no evidence
    at all (`rows` empty) - a considered refusal must never be turned into an
    answer by this guard.
    """
    if not rows:
        return rows
    dominant = _dominant_directory_row(message, raw_rows, target_country_names)
    if dominant is None:
        return rows
    dominant_row, _dominant_score = dominant
    dominant_id = str(dominant_row.get("id") or "")
    if rows and str(rows[0][0].get("id") or "") == dominant_id:
        return rows
    remainder = [pair for pair in rows if str(pair[0].get("id") or "") != dominant_id]
    return [dominant, *remainder]


def _vector_query(message: str, country: str, language: str, *, scope: str = "locale") -> dict[str, Any]:
    """Build a vector query with metadata filters."""
    return {
        "size": settings.OPENSEARCH_CANDIDATE_COUNT,
        "query": {
            "knn": {
                "embedding": {
                    "vector": embed_text(message),
                    "k": settings.OPENSEARCH_CANDIDATE_COUNT,
                    "filter": {
                        "bool": {
                            "filter": [
                                _scope_filter(country, language, scope),
                                {"term": {"status": "active"}},
                                *_generation_filters(country, language, scope),
                            ]
                        }
                    },
                }
            }
        }
    }


def _is_adjacent_letter_swap(token: str, market_name: str) -> bool:
    """True when ``token`` is ``market_name`` with one pair of neighbouring letters swapped."""
    if len(token) != len(market_name):
        return False
    differences = [index for index, (left, right) in enumerate(zip(token, market_name)) if left != right]
    return (
        len(differences) == 2
        and differences[1] == differences[0] + 1
        and token[differences[0]] == market_name[differences[1]]
        and token[differences[1]] == market_name[differences[0]]
    )


def _directory_target_country_names(message: str, selected_country: str) -> set[str]:
    """Return the named market(s) whose global directory record should lead.

    A named country served by a configured shared office and without a market
    entry of its own adds that office's ``record_country`` instead of falling
    back to the selected market.
    """
    catalog = [*load_market_config().get("markets", []), *load_global_directory_markets()]
    mentioned_codes = find_market_mentions(message)
    shared_record_countries = find_shared_office_record_countries(message)
    if not mentioned_codes and not shared_record_countries:
        normalized_message = _normalize_text(message)
        message_tokens = [token for token in normalized_message.split() if len(token) >= 4]
        for market in catalog:
            market_name = _normalize_text(str(market.get("name") or ""))
            name_tokens = market_name.split()
            if len(name_tokens) != 1 or not market_name:
                continue
            # Only one swapped pair of neighbouring letters counts as a typo
            # ("Mexcio"). A similarity ratio matched ordinary words to markets
            # ("being" -> Benin, "child" -> Chile) and put a foreign directory
            # target on company-policy questions (live, SE buy-back turns).
            if len(market_name) >= 5 and any(
                _is_adjacent_letter_swap(token, market_name) for token in message_tokens
            ):
                mentioned_codes.add(str(market.get("code") or "").upper())
    # With no country named, the session's own record is the target for
    # contact/sponsoring wording. Its operational fields (delivery cost,
    # minimum order amount, payment methods) fall back to it too, but only for
    # a market whose directory record is configured by name in
    # global_directory_markets.json (NL -> "Netherlands Benelux"); other
    # markets keep company-policy-only scope for these fields. Policy wording
    # never falls back.
    own_market_field = (
        str(selected_country or "").upper()
        in {str(market.get("code") or "").upper() for market in load_global_directory_markets()}
        and bool(OWN_MARKET_DIRECTORY_FIELD_RE.search(message or ""))
        and not DIRECTORY_POLICY_WORDING_RE.search(message or "")
    )
    if (
        not mentioned_codes
        and not shared_record_countries
        and not _GLOBAL_DIRECTORY_INTENT_RE.search(message or "")
        and not own_market_field
    ):
        return set()
    target_codes = mentioned_codes or (set() if shared_record_countries else {str(selected_country or "").upper()})
    return {
        str(country.get("name") or "")
        for country in catalog
        if str(country.get("code") or "").upper() in target_codes
    } | shared_record_countries


def _directory_target_section_names(message: str, selected_country: str) -> set[str]:
    """Return ``_directory_target_country_names()``'s result, with any country
    named by the International Sponsoring Directory's own alias table
    (``config/sponsoring_directory_country_aliases.json``) relabelled to that
    table's section name instead of its generic, ISO-code-based market name.

    The directory's own PDF section headings sometimes group or spell a
    country differently than the generic catalog does (e.g. "UK" -> the
    generic "United Kingdom" market, but the directory's own section is
    "England"; "Eswatini" has no section of its own and is served by
    "South Africa"'s). This layers that relabelling on top of
    ``_directory_target_country_names()`` rather than replacing its result
    wholesale: only the specific country/countries an alias term actually
    matched are substituted (its own generic name removed, the alias table's
    section name added); every other country the base function found stays
    exactly as it was. A message naming two countries, only one of which the
    alias table covers ("Compare Uganda and Dubai delivery times"), keeps
    both - Uganda untouched, Dubai's "United Arab Emirates" replacing nothing
    since Dubai/Saudi Arabia/etc. are not otherwise named markets here.

    A matched alias term supersedes a market code's generic name only when
    that exact term is *itself* unambiguously recognized by
    ``find_market_mentions`` as naming that code
    (``superseded_market_codes_for_alias_term()``) - i.e. it is genuinely
    the same market under a different spelling/bundling ("United Kingdom" is
    both an England-group term and GB's own configured name), never merely
    a short word that happens to be a substring of some unrelated market's
    longer name. Review round 3: an earlier, looser containment check here
    (matching a term against ANY of a code's name/alias variants by
    substring) lost a genuinely co-mentioned country whenever a matched
    term happened to sit inside an unrelated code's longer name - "China"
    (matched via the China alias group) is a substring of Hong Kong's own
    localized "Hong Kong SAR China", "American" (from the North America
    group) is a prefix of "American Samoa", "Netherlands" (from the
    Netherlands Benelux group) is a prefix of "Netherlands Antilles" - each
    wrongly deleted the second, unrelated country from a two-country
    message. ``find_market_mentions`` never makes that mistake (it requires
    an exact, unambiguous whole-name match), so deferring to it here avoids
    reintroducing this bug through a different path.

    This is a separate function, not a parameter on
    ``_directory_target_country_names()``, so every other caller of that
    function (there is currently one, the query planner's own-market-field
    fallback in ``app/retrieval/providers.py``) keeps asking its original,
    narrower question with no code change and no opt-out flag to remember -
    only the real directory search below calls this one.
    """
    term_matches = find_sponsoring_directory_alias_matches(message)
    if not term_matches:
        return _directory_target_country_names(message, selected_country)
    generic_names = _directory_target_country_names(message, selected_country)
    if not find_market_mentions(message) and not find_shared_office_record_countries(message):
        # No country was actually named by the generic mechanism (only by
        # the alias table). Whatever `generic_names` holds - empty, or the
        # base function's own "no country named" fallback to the session's
        # *selected* market for contact/sponsoring wording - does not
        # describe a country this message actually mentioned, so it must not
        # survive alongside the alias table's real match (otherwise, e.g., a
        # "St Barthelemy office phone?" question from a US-market session
        # would wrongly keep "United States" next to "St Marteen & St
        # Barthelemy").
        generic_names = set()
    catalog = [*load_market_config().get("markets", []), *load_global_directory_markets()]
    code_name_variants: dict[str, set[str]] = {}
    for market in catalog:
        code = str(market.get("code") or "").upper()
        name = str(market.get("name") or "")
        if code and name:
            code_name_variants.setdefault(code, set()).add(name)
    result = set(generic_names)
    for term, record_country in term_matches:
        for code in superseded_market_codes_for_alias_term(term):
            result.difference_update(code_name_variants.get(code, ()))
        result.add(record_country)
    return result


def _record_country_filter(country_names: set[str]) -> dict[str, Any] | None:
    """Build a case-tolerant filter for explicitly requested global records."""
    names = sorted({_normalize_text(name) for name in country_names if _normalize_text(name)})
    if not names:
        return None
    should: list[dict[str, Any]] = []
    for name in names:
        should.extend(
            [
                exact_term_query("metadata.record_country", name),
                {"match_phrase": {"metadata.record_country": {"query": name}}},
            ]
        )
    return {"bool": {"should": should, "minimum_should_match": 1}}


# Common function words per section language, accent-folded. One of them in the
# question means it is written in the section's language, so it is not a
# translation and the translated-query rescue does not apply. Each list omits
# words that are also common in the other listed languages or in es/pt/it
# (English "is"/"in"/"we"/"of" are Dutch, "also"/"was"/"an" German, "a"/"as"/"on"
# French or Romance), so a genuine translation is not blocked by a shared word.
# A section language with no list gets no rescue: its language cannot be told apart.
SECTION_LANGUAGE_MARKERS: dict[str, frozenset[str]] = {
    "en": frozenset({
        "the", "my", "your", "our", "their", "you", "they", "can", "could", "would", "should", "must",
        "how", "what", "which", "who", "why", "where", "when", "does", "did", "are", "have", "and",
        "with", "about", "this", "that", "these", "those", "there", "from", "into", "any", "not", "to",
        "for", "it", "if", "be", "been", "get", "much", "many",
    }),
    "nl": frozenset({
        "het", "een", "ik", "mijn", "jouw", "uw", "hoe", "wat", "welke", "waarom", "wanneer", "hoeveel",
        "waar", "kan", "kunnen", "mag", "moet", "zijn", "van", "voor", "niet", "ook", "maar", "bij",
        "naar", "deze", "dat", "wordt", "worden", "heb", "hebben", "heeft", "wij", "zij", "mij", "ons",
        "geen", "wel", "nog",
    }),
    "fr": frozenset({
        "une", "est", "sont", "mon", "votre", "nous", "vous", "comment", "combien", "pourquoi", "quand",
        "quel", "quelle", "quels", "quelles", "peut", "peux", "puis", "avec", "pour", "dans", "sur", "pas",
        "cette", "aux", "au", "et", "suis", "etre", "avoir", "faire", "sa", "ses", "leur", "leurs", "ils",
        "elle",
    }),
    "de": frozenset({
        "der", "ein", "eine", "einen", "einem", "ist", "sind", "ich", "mein", "meine", "mich", "mir",
        "warum", "wann", "wieviel", "viel", "kann", "konnen", "darf", "muss", "mit", "und", "nicht",
        "fur", "auch", "oder", "bei", "wenn", "wird", "habe", "haben", "zu", "von", "dem", "sich", "kein",
        "keine", "unser", "ihr", "ihre", "wo", "wer", "welche", "welcher", "bitte",
    }),
}
# Markers spelled exactly like common English words ("a delivery van", "fur", "sa",
# "mon", "mag"). Written in that exact form they are not evidence that a question
# is a translation (Fable W8b note 3). They stay in SECTION_LANGUAGE_MARKERS, so the
# section-language check still reads them and the rescue can only become rarer.
TRANSLATION_EVIDENCE_HOMOGRAPHS: frozenset[str] = frozenset({"van", "fur", "sa", "mon", "mag"})


def _question_in_section_language(message: str, section_language: str) -> bool:
    """True unless the question is verifiably written in a language other than the section's.

    Static and local: the question counts as the section's language when it
    contains any SECTION_LANGUAGE_MARKERS word for that language, or when that
    language has no marker list. W8 review: "Can my spouse also join as a
    distributor?" against the English NL licence section was rescued (0.6625).
    """
    markers = SECTION_LANGUAGE_MARKERS.get(_marker_language(section_language))
    if not markers:
        return True
    return bool(_folded_words(message) & markers)


def _question_in_another_listed_language(message: str, section_language: str) -> bool:
    """True when the question carries a SECTION_LANGUAGE_MARKERS word of a language other than the section's.

    Positive evidence of translation. Absence of the section language's markers
    alone is not enough: "Is a spouse allowed as distributor?" uses no listed
    English word and was still rescued (W8 review finding 2, 0.6625).

    Names say nothing about the question's language, so words written as names
    ("Van de Berg", "? Bitte.") are not evidence, and neither is a word spelled
    exactly like an English one in TRANSLATION_EVIDENCE_HOMOGRAPHS ("a delivery
    van", "fur"); "für" still is (Fable W8b note 3).
    """
    section = _marker_language(section_language)
    written = re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", message or "").casefold(), flags=re.UNICODE)
    words = _folded_words(" ".join(word for word in written if word not in TRANSLATION_EVIDENCE_HOMOGRAPHS))
    words -= _question_name_tokens(message)
    return any(words & markers for language, markers in SECTION_LANGUAGE_MARKERS.items() if language != section)


def _marker_language(language: str) -> str:
    return re.split(r"[-_]", str(language or "").casefold())[0]


def _folded_words(message: str) -> set[str]:
    decomposed = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", message or "")).casefold()
    folded = "".join(character for character in decomposed if not unicodedata.combining(character))
    return set(re.findall(r"[^\W_]+", folded, flags=re.UNICODE))


def _question_name_tokens(message: str) -> set[str]:
    """Tokens written as names in the question: acronyms, numbers, capitalised non-initial words.

    Names ("Forever", "FBO") survive translation unchanged, so they say nothing
    about which language the question is written in.
    """
    words = re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", message or ""), flags=re.UNICODE)
    names = {
        word
        for index, word in enumerate(words)
        if any(character.isdigit() for character in word)
        or (len(word) >= 2 and word.isupper())
        or (index > 0 and word[:1].isupper())
    }
    return _tokens(" ".join(names))


def _translated_query_local_relevance(
    message: str,
    country: str,
    document: RetrievedDocument,
    planned_queries: list[str],
    candidate_rows: list[tuple[dict[str, Any], float]],
) -> float:
    """Local relevance of the session market's own policy section through a translated planner query.

    A Dutch question scored against the English edition of the right NL section
    shares only names with it, so its lexical relevance misses the strong-match
    rescue that the same question passes against the Dutch edition (live: 0.4234
    vs 0.5134, threshold 0.44). No question-language signal exists, so a planner
    query stands in only when the question's ordinary (non-name) words appear in
    none of: the chosen section, any retrieved candidate in that section's
    language, and the planner query itself. Returns 0.0 for directory records,
    global rows and other markets' sections.
    """
    metadata = document.metadata or {}
    if (
        metadata.get("access_scope") == "global"
        or metadata.get("document_type") in GLOBAL_DIRECTORY_DOCUMENT_TYPES
        or str(document.country or "").upper() not in {code.upper() for code in get_document_country_codes(country)}
    ):
        return 0.0
    if _question_in_section_language(message, document.language):
        # Not a translation: the question's own lexical relevance stands.
        return 0.0
    if not _question_in_another_listed_language(message, document.language):
        # No positive sign of another language either, so still not a translation.
        return 0.0
    ordinary_words = _tokens(message) - _question_name_tokens(message)
    if not ordinary_words:
        return 0.0
    same_language_text = " ".join(
        [
            document.title,
            document.content,
            document.excerpt,
            *(
                f"{row.get('section_title') or ''} {row.get('content') or ''}"
                for row, _score in candidate_rows
                if str(row.get("language") or "") == document.language
            ),
        ]
    )
    if ordinary_words & _tokens(same_language_text):
        return 0.0
    return max(
        (
            _document_relevance(query, document)
            for query in planned_queries
            if query and not ordinary_words & _tokens(query)
        ),
        default=0.0,
    )


def _hit_to_row(hit: dict[str, Any], *, score_weight: float = 1.0) -> dict[str, Any]:
    """Convert an OpenSearch hit to the row shape used by section scoring."""
    source = hit.get("_source", {}) or {}
    return {
        "id": source.get("id") or hit.get("_id", ""),
        "source_file": source.get("source_file", ""),
        "source_uri": source.get("source_uri", ""),
        "country": source.get("country", ""),
        "language": source.get("language", ""),
        "document_type": source.get("document_type", ""),
        "access_scope": source.get("access_scope", "country"),
        "document_version": source.get("document_version", ""),
        "effective_date": source.get("effective_date", ""),
        "chunk_type": source.get("chunk_type", "section"),
        "parent_section_id": source.get("parent_section_id", ""),
        "section_id": source.get("section_id", ""),
        "section_title": source.get("section_title", ""),
        "start_page": source.get("start_page", ""),
        "end_page": source.get("end_page", ""),
        "content": source.get("content", ""),
        "search_text": source.get("search_text", ""),
        "metadata": {
            "status": "active",
            **(source.get("metadata") or {}),
            **{key: source[key] for key in (
                "ingestion_id", "logical_document_id", "content_hash", "source_file",
                "effective_date", "expiry_date", "status",
            ) if key in source},
        },
        "rank": float(hit.get("_score") or 0.0) * score_weight,
    }


_SELECTOR_HEADING_CHARS = 160
_SELECTOR_HIDDEN_CLAUSE_LIMIT = 8
_SELECTOR_SECTION_PREFIX_RE = re.compile(r"section\s+(\S+?):\s*(\S.*)$", re.IGNORECASE)
_SELECTOR_CLAUSE_MARKER_RE = re.compile(r"^[ \t]*\(?([a-z]|[ivx]{2,4})\)[ \t]", re.MULTILINE)


def _selector_heading_path(row: dict[str, Any]) -> tuple[str, str]:
    """Return a child chunk's governing heading path and its text without the heading line.

    The extractor writes a child's governing heading as its first content line,
    ``Section <parent>: <heading>``, while ``section_title`` holds the clause's
    own first line. Near-identical clauses from different sections therefore
    differ only inside the text. Lifting that verified line into the header
    keeps clause, heading and section identity together at no text cost.
    Any other row, including one whose heading is longer than the header
    allows, keeps its content unchanged, so no previously visible text is lost.

    The path is read from the row's own content, not from parent metadata: it
    relies on the extractor's ``Section <id>:`` first-line convention. The id
    in that line must be the row's parent or a prefix of the row's own id, but
    it is what the header shows. Scope never depends on it: country, language
    and access filters are applied before any view is built.
    """
    content = str(row.get("content") or "")
    parent_id = str(row.get("parent_section_id") or "")
    first_line, separator, body = content.partition("\n")
    match = _SELECTOR_SECTION_PREFIX_RE.match(first_line.strip())
    if not parent_id or not separator or match is None:
        return "", content
    prefix_id, heading = match.group(1), match.group(2).strip()
    section_id = str(row.get("section_id") or "")
    if prefix_id != parent_id and not section_id.startswith(f"{prefix_id}-"):
        return "", content
    if len(heading) > _SELECTOR_HEADING_CHARS:
        return "", content
    path = f"{prefix_id} {heading}"
    clause = _SELECTOR_CLAUSE_MARKER_RE.match(body)
    if clause:
        path = f"{path} > ({clause.group(1)})"
    return path, body


def _selector_truncation_notice(text: str, shown: int) -> str:
    """Say that the selector sees only part of the text, and which clauses it misses.

    Without this, a clause cut off mid-sentence reads as complete and a
    directory field beyond the view reads as absent. The notice is bounded and
    never replaces visible text.
    """
    if len(text) <= shown:
        return ""
    hidden = [f"({match.group(1)})" for match in _SELECTOR_CLAUSE_MARKER_RE.finditer(text, shown)]
    hidden = list(dict.fromkeys(hidden))
    notice = f"[Text truncated: {shown} of {len(text)} characters shown"
    visible = list(_SELECTOR_CLAUSE_MARKER_RE.finditer(text, 0, shown))
    next_start = next((match.start() for match in _SELECTOR_CLAUSE_MARKER_RE.finditer(text, shown)), len(text))
    if visible and text[shown:next_start].strip():
        notice += f"; clause ({visible[-1].group(1)}) continues"
    if hidden:
        listed = ", ".join(hidden[:_SELECTOR_HIDDEN_CLAUSE_LIMIT])
        more = ", ..." if len(hidden) > _SELECTOR_HIDDEN_CLAUSE_LIMIT else ""
        notice += f"; clauses not shown: {listed}{more}"
    return f"{notice}]"


def _selector_candidate_text(row: dict[str, Any], score: float, index: int) -> str:
    """Format one candidate for the evidence selector."""
    metadata = dict(row.get("metadata") or {})
    heading_path, text = _selector_heading_path(row)
    lines = [
        f"Candidate {index}",
        f"Document type: {row.get('document_type', '')}",
        f"Access scope: {row.get('access_scope', 'country')}",
        f"Record type: {metadata.get('directory_section', '')}",
        f"Record country: {metadata.get('record_country', '')}",
        f"Section: {row.get('section_id', '')}",
    ]
    if heading_path:
        lines.append(f"Heading path: {heading_path}")
    lines.extend(
        [
            f"Title: {row.get('section_title', '')}",
            f"Current score: {score}",
            f"Text:\n{text[:_SELECTOR_VIEW_CHARS]}",
        ]
    )
    notice = _selector_truncation_notice(text, _SELECTOR_VIEW_CHARS)
    if notice:
        lines.append(notice)
    return "\n".join(lines)


def _selector_candidates(
    rows: list[tuple[dict[str, Any], float]],
    limit: int,
) -> list[tuple[dict[str, Any], float]]:
    """Keep top-ranked evidence while reserving room for global documents."""
    candidates = rows[:limit]
    global_rows = [pair for pair in rows if pair[0].get("access_scope") == "global"]
    if not global_rows or limit < 2:
        return candidates

    global_quota = min(len(global_rows), max(1, limit // 3))
    selected_global_ids = {
        str(row.get("id") or "")
        for row, _score in candidates
        if row.get("access_scope") == "global"
    }
    missing_global = [
        pair
        for pair in global_rows
        if str(pair[0].get("id") or "") not in selected_global_ids
    ][: max(0, global_quota - len(selected_global_ids))]
    if not missing_global:
        return candidates

    replacement_count = len(missing_global)
    retained: list[tuple[dict[str, Any], float]] = []
    removable = replacement_count
    for pair in reversed(candidates):
        if removable and pair[0].get("access_scope") != "global":
            removable -= 1
            continue
        retained.append(pair)
    retained.reverse()
    return [*retained, *missing_global]


def _parse_selector_ranks(text: str) -> list[int]:
    """Parse selected candidate ranks from a compact JSON model response."""
    stripped = text.strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            payload = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return []

    parsed: list[int] = []
    for rank in payload.get("selected_ranks", []):
        try:
            parsed_rank = int(rank)
        except (TypeError, ValueError):
            continue
        if parsed_rank not in parsed:
            parsed.append(parsed_rank)
    return parsed


def _parse_selector_confidence(value: object) -> float | None:
    """Clamp the selector's self-reported top-rank confidence to [0, 1].

    Missing or unparseable values return None so callers fall back to the
    lexical confidence calculation, rather than treating a malformed field
    as zero confidence.
    """
    try:
        confidence = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if confidence != confidence:  # NaN never equals itself
        return None
    return max(0.0, min(confidence, 1.0))


def _parse_selector_decision(
    text: str,
) -> tuple[list[int], bool | None, float | None, bool | None] | None:
    """Parse a selector decision while distinguishing rejection from failure."""
    stripped = text.strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            payload = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    relevant = payload.get("relevant_evidence")
    if relevant is not True and relevant is not False and relevant is not None:
        return None
    confidence = _parse_selector_confidence(payload.get("top_rank_confidence"))
    directly_answers = payload.get("directly_answers_top_rank")
    if directly_answers is not True and directly_answers is not False:
        directly_answers = None
    return _parse_selector_ranks(json.dumps(payload)), relevant, confidence, directly_answers


# The selector reads only the first 1,200 characters of a section.  When it
# keeps a country-policy section, bind one uniquely best child clause that was
# already inside that view, without changing the selector's first choice.
_SELECTOR_VIEW_CHARS = 1200
_BOUND_CHILD_DOCUMENT_KEYS = ("source_file", "country", "language", "access_scope")


def _same_document(parent: dict[str, Any], child: dict[str, Any]) -> bool:
    """Return whether both rows belong to the same source, country and language."""
    if not str(parent.get("source_file") or ""):
        return False
    return all(str(parent.get(key) or "") == str(child.get(key) or "") for key in _BOUND_CHILD_DOCUMENT_KEYS)


def _clause_in_selector_view(parent: dict[str, Any], child: dict[str, Any]) -> bool:
    """Return whether the child clause is already in the selector's parent view."""
    content = str(child.get("content") or "")
    first_line, separator, body = content.partition("\n")
    prefix = f"section {str(parent.get('section_id') or '').casefold()}:"
    if separator and first_line.strip().casefold().startswith(prefix):
        content = body
    clause = " ".join(content.split())
    view = " ".join(str(parent.get("content") or "")[:_SELECTOR_VIEW_CHARS].split())
    return bool(clause) and clause in view


def _strictly_best(pairs: list[tuple[dict[str, Any], float]]) -> tuple[dict[str, Any], float] | None:
    """Return one highest-scoring pair, or ``None`` when the score is tied."""
    if not pairs:
        return None
    ordered = sorted(pairs, key=lambda pair: pair[1], reverse=True)
    if len(ordered) > 1 and ordered[0][1] == ordered[1][1]:
        return None
    return ordered[0]


def _bindable_parent(row: dict[str, Any]) -> bool:
    return (
        row.get("chunk_type") == "section"
        and row.get("document_type") == "policy"
        and row.get("access_scope") == "country"
    )


def _bindable_child(row: dict[str, Any]) -> bool:
    return (
        row.get("chunk_type") == "list_item"
        and row.get("document_type") == "policy"
        and row.get("access_scope") == "country"
    )


def _bound_child(
    parent: dict[str, Any], rows: list[tuple[dict[str, Any], float]]
) -> tuple[dict[str, Any], float] | None:
    """Return the uniquely best eligible child from the parent section."""
    parent_id = str(parent.get("section_id") or "")
    if not parent_id or not _bindable_parent(parent):
        return None
    children = [
        pair
        for pair in rows
        if _bindable_child(pair[0])
        and str(pair[0].get("parent_section_id") or "") == parent_id
        and _same_document(parent, pair[0])
        and _clause_in_selector_view(parent, pair[0])
    ]
    return _strictly_best(children)


def _displaceable_position(
    selected: list[tuple[dict[str, Any], float]], protected_ids: set[str]
) -> int | None:
    """Return a non-top selected position that a bound child may replace."""
    for position in range(len(selected) - 1, 0, -1):
        if str(selected[position][0].get("id") or "") not in protected_ids:
            return position
    return None


def _bind_selected_parent_children(rows: list[tuple[dict[str, Any], float]]) -> list[tuple[dict[str, Any], float]]:
    """Bind verified country-policy children without reordering selector choices."""
    if not settings.OPENSEARCH_EVIDENCE_SELECTOR_ENABLED or not rows:
        return rows
    selected_count = 0
    for row, _score in rows:
        if not row.get("evidence_selector_selected"):
            break
        selected_count += 1
    if not selected_count:
        return rows

    selected = list(rows[:selected_count])
    remaining = list(rows[selected_count:])
    displaced: list[tuple[dict[str, Any], float]] = []
    protected_ids: set[str] = set()
    for parent, _score in rows[:selected_count]:
        # An earlier binding may have displaced this parent; it no longer
        # holds a selected position, so it must not bring its child back.
        if not any(row is parent for row, _ in selected):
            continue
        child_pair = _bound_child(parent, rows)
        if child_pair is None:
            continue
        child_id = str(child_pair[0].get("id") or "")
        if any(str(row.get("id") or "") == child_id for row, _ in selected):
            continue
        pair_ids = protected_ids | {str(parent.get("id") or ""), child_id}
        position: int | None = None
        popped: tuple[dict[str, Any], float] | None = None
        if len(selected) >= settings.OPENSEARCH_RESULT_COUNT:
            position = _displaceable_position(selected, pair_ids)
            if position is None:
                continue
            popped = selected.pop(position)
        parent_position = next((index for index, (row, _) in enumerate(selected) if row is parent), None)
        if parent_position is None:
            if popped is not None and position is not None:
                selected.insert(position, popped)
            continue
        if popped is not None:
            displaced.insert(0, popped)
        protected_ids = pair_ids
        child_pair[0]["parent_bound_child"] = True
        selected.insert(parent_position + 1, child_pair)
        remaining = [pair for pair in remaining if pair[0] is not child_pair[0]]
        # A selector-picked child can already sit in `displaced` (an earlier
        # binding pushed it out of `selected`) when its own parent binds it
        # here; without this it would be emitted twice.
        displaced = [pair for pair in displaced if pair[0] is not child_pair[0]]
    return [*selected, *displaced, *remaining]


class OpenSearchSectionProvider:
    """Retrieve approved document sections from an OpenSearch section index."""

    def __init__(
        self,
        index_name: str | None = None,
        *,
        enable_bedrock_rerank: bool = False,
    ) -> None:
        self.index_name = index_name or settings.OPENSEARCH_INDEX
        self.enable_bedrock_rerank = enable_bedrock_rerank

    def _search_channel(
        self,
        client: OpenSearch,
        *,
        kind: str,
        body: dict[str, Any],
        correlation_id: str,
        rank_record: dict[str, Any] | None,
        query_index: int | None = None,
        weight: float = 1.0,
    ) -> tuple[dict[str, Any] | None, str | None, list[dict[str, Any]]]:
        """Run one search channel and preserve a typed provider failure state.

        Query/request errors remain visible for diagnosis. Transport and other
        provider failures are returned to the caller as a failed channel, so
        healthy channels can still provide evidence.
        """
        try:
            response = client.search(index=self.index_name, body=body)
        except (ConnectionError, AuthenticationException, AuthorizationException):
            LOGGER.exception(
                "opensearch_section_search_failed",
                correlation_id=correlation_id,
                channel=kind,
            )
            return None, kind, [{"channel": kind, "reason": "transport_exception"}]
        except TransportError as exc:
            status_code = getattr(exc, "status_code", None)
            is_service_failure = isinstance(status_code, int) and 500 <= status_code < 600
            if isinstance(exc, (RequestError, NotFoundError, ConflictError)) or not is_service_failure:
                raise
            LOGGER.exception(
                "opensearch_section_search_failed",
                correlation_id=correlation_id,
                channel=kind,
            )
            return None, kind, [{"channel": kind, "reason": "service_exception"}]
        response_failures = self._response_failures(response, kind)
        _record_rank_list_search(rank_record, kind, query_index, weight, response)
        return response, kind if response_failures else None, response_failures

    @staticmethod
    def _response_failures(response: dict[str, Any], kind: str) -> list[dict[str, Any]]:
        """Classify truthful partial OpenSearch responses without hiding bad requests.

        OpenSearch can return hits together with a timeout or failed shards.
        Those hits are valid but incomplete only for a verified transient or
        service-side failure. Query, mapping, index, and unknown shard errors
        remain visible to callers instead of becoming an availability state.
        """
        failures: list[dict[str, Any]] = []
        if response.get("timed_out") is True:
            failures.append({"channel": kind, "reason": "timed_out"})

        shards = response.get("_shards")
        if shards is None:
            return failures
        if not isinstance(shards, dict):
            raise RequestError(400, "invalid OpenSearch shard response", {"_shards": shards})
        failed = shards.get("failed", 0)
        if isinstance(failed, bool) or not isinstance(failed, int) or failed < 0:
            raise RequestError(400, "invalid OpenSearch failed shard count", {"_shards": shards})
        if not failed:
            return failures

        shard_failures = shards.get("failures")
        if not isinstance(shard_failures, list) or not shard_failures:
            raise RequestError(500, "OpenSearch shard failure without diagnostics", {"_shards": shards})
        if len(shard_failures) != failed:
            raise RequestError(
                500,
                "OpenSearch shard failure with incomplete diagnostics",
                {"_shards": shards},
            )

        for position, failure in enumerate(shard_failures, start=1):
            if not isinstance(failure, dict):
                raise RequestError(400, "invalid OpenSearch shard failure", {"failure": failure})
            reason = failure.get("reason")
            error_type = reason.get("type") if isinstance(reason, dict) else None
            status = failure.get("status")
            has_status = isinstance(status, int) and not isinstance(status, bool)
            failure_label = error_type if isinstance(error_type, str) else "unclassified_shard_failure"
            failure_context = {
                "_shards": shards,
                "failure": failure,
                "failure_position": position,
            }
            if (
                failure_label in _SHARD_CONFIGURATION_FAILURE_TYPES
                or has_status and 400 <= status < 500
            ):
                raise RequestError(
                    400,
                    f"OpenSearch shard failure: {failure_label}",
                    failure_context,
                )
            is_transient = failure_label in _TRANSIENT_SHARD_FAILURE_TYPES
            is_service_failure = has_status and 500 <= status < 600
            if not is_transient and not is_service_failure:
                raise RequestError(
                    500,
                    f"OpenSearch shard failure: {failure_label}",
                    failure_context,
                )

        failures.append({"channel": kind, "reason": "shard_failure", "failed_shards": failed})
        return failures

    def _retrieve_channel_hits(
        self,
        client: OpenSearch,
        *,
        message: str,
        country: str,
        language: str,
        correlation_id: str,
        search_plan: RetrievalQueryPlan,
        rank_record: dict[str, Any] | None,
        target_country_names: set[str],
        explicit_section_id: str | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, list[str], list[dict[str, Any]], int]:
        """Collect independent search channels without collapsing outages into empties."""
        text_hits: list[dict[str, Any]] = []
        vector_hits: list[dict[str, Any]] = []
        failed_channels: list[str] = []
        failure_details: list[dict[str, Any]] = []
        successful_searches = 0

        def collect(
            kind: str,
            body: dict[str, Any],
            target: list[dict[str, Any]],
            *,
            query_index: int | None = None,
            weight: float = 1.0,
            weighted: bool = False,
        ) -> dict[str, Any] | None:
            nonlocal successful_searches
            response, failed_channel, channel_failures = self._search_channel(
                client,
                kind=kind,
                body=body,
                correlation_id=correlation_id,
                rank_record=rank_record,
                query_index=query_index,
                weight=weight,
            )
            successful_searches += int(response is not None)
            if failed_channel:
                failed_channels.append(failed_channel)
            failure_details.extend(channel_failures)
            target.extend(_weighted_search_hits(response, weight) if weighted else _search_hits(response))
            return response

        if explicit_section_id:
            exact, failed_channel, channel_failures = self._search_channel(
                client,
                kind="exact",
                body=_exact_section_query(explicit_section_id, country, language),
                correlation_id=correlation_id,
                rank_record=rank_record,
            )
            successful_searches += int(exact is not None)
            if failed_channel:
                failed_channels.append(failed_channel)
            failure_details.extend(channel_failures)
            text_hits.extend(
                {**hit, "_score": max(float(hit.get("_score") or 0.0), 100.0)}
                for hit in _search_hits(exact)
            )
        for index, search_message in enumerate(search_plan.queries):
            weight = 1.0 if index == 0 else 0.88
            collect(
                "text",
                _text_query(search_message, country, language, scope="locale"),
                text_hits,
                query_index=index,
                weight=weight,
                weighted=True,
            )
            collect(
                "vector",
                _vector_query(search_message, country, language, scope="locale"),
                vector_hits,
                query_index=index,
                weight=weight,
                weighted=True,
            )
        if search_plan.prefer_outline:
            collect("outline", _outline_text_query(message, country, language), text_hits)

        global_search_message = ""
        if search_plan.include_global_documents:
            global_search_message = self._global_search_query(message, language, correlation_id)
            collect(
                "global_text",
                _directory_text_query(global_search_message, target_country_names),
                text_hits,
            )
            global_vector_query = _vector_query(global_search_message, country, language, scope="global")
            country_filter = _record_country_filter(target_country_names)
            if country_filter is not None:
                global_vector_query["query"]["knn"]["embedding"]["filter"]["bool"]["filter"].append(
                    country_filter
                )
            collect("global_vector", global_vector_query, vector_hits)
        return text_hits, vector_hits, global_search_message, failed_channels, failure_details, successful_searches

    def retrieve(self, message: str, country: str, language: str, role: str, correlation_id: str) -> RetrievalResult:
        del role
        _start_generation_lookup_signal()
        rank_record = _start_rank_list_record()
        search_plan = self._build_search_plan(message, country, language, correlation_id)
        if search_plan.client_action:
            return RetrievalResult(
                documents=[],
                citations=[],
                confidence=1.0,
                metadata={
                    "provider": "opensearch_section",
                    "client_action": search_plan.client_action,
                    "conversation_intent": "support_request",
                    "intent_confidence": search_plan.intent_confidence,
                },
            )
        # A reviewed policy-safety question - asking what the rules prohibit -
        # must still reach the documents. Skipping retrieval here leaves the
        # request with no evidence, so it is refused downstream no matter what
        # the routing layers decide. Verified live 2026-09-07: the planner
        # classifies these as medical_claim/income_claim and this branch, not
        # the guardrails, is what withheld the answer.
        if (
            search_plan.conversation_intent != "knowledge"
            and search_plan.intent_confidence >= settings.BEDROCK_CONVERSATION_ROUTE_MIN_CONFIDENCE
            and not is_policy_safety_question(message)
        ):
            return RetrievalResult(
                documents=[],
                citations=[],
                confidence=1.0,
                metadata={
                    "provider": "opensearch_section",
                    "conversation_intent": search_plan.conversation_intent,
                    "conversation_subtype": search_plan.conversation_subtype,
                    "intent_confidence": search_plan.intent_confidence,
                },
            )
        client = _client()
        search_messages = search_plan.queries
        target_country_names = _directory_target_section_names(message, country)
        explicit_section_id = _section_reference(message)
        text_hits, vector_hits, global_search_message, failed_search_channels, failure_details, successful_searches = (
            self._retrieve_channel_hits(
                client,
                message=message,
                country=country,
                language=language,
                correlation_id=correlation_id,
                search_plan=search_plan,
                rank_record=rank_record,
                target_country_names=target_country_names,
                explicit_section_id=explicit_section_id,
            )
        )

        if failed_search_channels and not successful_searches:
            return RetrievalResult(
                documents=[],
                citations=[],
                confidence=0.0,
                metadata={
                    "provider": "opensearch_section",
                    "failed_search_channels": failed_search_channels,
                    "search_channel_failures": failure_details,
                    **_generation_lookup_fields(),
                    **_rank_list_fields(rank_record, search_plan=search_plan, target_country_names=target_country_names),
                },
                availability=RetrievalAvailability.UNAVAILABLE,
            )

        failure_metadata = (
            {
                "failed_search_channels": failed_search_channels,
                "search_channel_failures": failure_details,
            }
            if failed_search_channels
            else {}
        )
        availability = (
            RetrievalAvailability.DEGRADED if failed_search_channels else RetrievalAvailability.AVAILABLE
        )

        typo_ranking_queries = safe_typo_ranking_queries(message, search_messages[1:])
        rows = self._merge_hits(
            text_hits,
            vector_hits,
            message,
            ranking_queries=typo_ranking_queries,
            prefer_outline=search_plan.prefer_outline,
            target_country_names=target_country_names,
        )
        if self.enable_bedrock_rerank:
            from .bedrock_reranker import rerank_rows

            rows = rerank_rows(message, rows, correlation_id=correlation_id)
        _record_rank_list_merged(rank_record, rows)
        raw_rows = rows
        rows = self._select_evidence_rows(message, rows, correlation_id)
        selector_rejected = bool(raw_rows) and not rows and settings.OPENSEARCH_EVIDENCE_SELECTOR_ENABLED
        # Deterministic guard: undo the selector demoting a dominant,
        # country-matched global directory record (see the guard
        # documentation above `_restore_dominant_directory_record`). Placed
        # after `selector_rejected` is computed so that one field stays fixed
        # at the selector's own original decision. Everything computed below
        # from `rows[0][0]` - `selector_applied`, `selector_confidence`,
        # `top_source_directly_answers`, and (through `selector_applied`)
        # `strong_local_match` and the blended `confidence` - is NOT
        # insulated from this guard: each reads the actual winning row's own
        # dict keys, so if this guard changes which row is first, those
        # fields honestly report whatever that row itself carries (e.g.
        # `selector_applied` can flip True->False when the restored row was
        # not one of the selector's own picks). That is intentional, not a
        # bug: the row should report its own truth, not the selector's.
        rows = _restore_dominant_directory_record(message, raw_rows, rows, target_country_names)
        rows = _bind_selected_parent_children(rows)

        eligible_rows = self._finalize_eligible_rows(rows)
        documents = [
            self._document_from_row(row, score) for row, score in eligible_rows
        ][: settings.OPENSEARCH_RESULT_COUNT]
        selector_applied = bool(rows and rows[0][0].get("evidence_selector_selected"))
        selector_confidence = rows[0][0].get("evidence_selector_confidence") if selector_applied else None
        top_source_directly_answers = (
            rows[0][0].get("evidence_selector_directly_answers") if selector_applied else None
        )
        max_local_relevance = _document_relevance(message, documents[0]) if documents else 0.0
        if (
            selector_applied
            and documents
            and max_local_relevance < settings.OPENSEARCH_SELECTOR_STRONG_MATCH_THRESHOLD
        ):
            # Only a question sharing no ordinary word with the chosen own-market
            # section can change here; every other question keeps its value.
            max_local_relevance = max(
                max_local_relevance,
                _translated_query_local_relevance(
                    message, country, documents[0], search_messages[1:], raw_rows
                ),
            )
        strong_local_match = bool(
            selector_applied
            and max_local_relevance >= settings.OPENSEARCH_SELECTOR_STRONG_MATCH_THRESHOLD
        )
        lexical_confidence = _confidence_from_documents(documents)
        # The evidence selector reads the actual candidate text and the
        # question together, so when it reports how confident it is in its
        # own top pick, that semantic judgment can see things raw lexical
        # scoring can't (a paraphrase with almost no shared vocabulary with
        # a correct, narrowly-worded policy clause). Never let it lower the
        # lexical score - only rescue a correct pick that scored low on
        # lexical grounds alone.
        confidence = (
            max(lexical_confidence, float(selector_confidence))
            if selector_confidence is not None
            else lexical_confidence
        )
        result = RetrievalResult(
            documents=documents,
            citations=[document.to_source() for document in documents],
            confidence=confidence,
            metadata={
                "provider": "opensearch_section",
                "candidate_count": len(raw_rows),
                "search_query_count": len(search_messages) + int(search_plan.include_global_documents),
                "typo_ranking_query_count": len(typo_ranking_queries),
                "typo_ranking_applied": bool(documents and documents[0].metadata.get("typo_ranking_applied")),
                "ranking_query_used": documents[0].metadata.get("ranking_query_used", "") if documents else "",
                "global_documents_searched": search_plan.include_global_documents,
                "outline_preferred": search_plan.prefer_outline,
                "client_action": search_plan.client_action,
                "conversation_intent": "knowledge",
                "global_query_translated": bool(global_search_message) and global_search_message != message,
                "explicit_section_reference": explicit_section_id,
                "evidence_selector_rejected": selector_rejected,
                "evidence_selector_applied": selector_applied,
                "evidence_selector_confidence": selector_confidence,
                "top_source_directly_answers": top_source_directly_answers,
                "lexical_confidence": lexical_confidence,
                "max_local_relevance": round(max_local_relevance, 6),
                "strong_local_match": strong_local_match,
                "parent_bound_children": [
                    document.metadata.get("section_id", "")
                    for document in documents
                    if document.metadata.get("parent_bound_child")
                ],
                **failure_metadata,
                "candidate_sources": [
                    self._document_from_row(row, score).to_source()
                    for row, score in raw_rows[: settings.OPENSEARCH_CANDIDATE_COUNT]
                ],
                **_generation_lookup_fields(),
                **_rank_list_fields(
                    rank_record,
                    raw_rows=raw_rows,
                    search_plan=search_plan,
                    target_country_names=target_country_names,
                ),
            },
            availability=availability,
        )
        LOGGER.info(
            "opensearch_section_retrieval_success",
            correlation_id=correlation_id,
            country=country,
            language=language,
            source_count=len(result.sources),
            candidate_count=len(raw_rows),
            confidence=result.confidence,
            typo_ranking_query_count=len(typo_ranking_queries),
            typo_ranking_applied=result.metadata["typo_ranking_applied"],
            ranking_query_used=result.metadata["ranking_query_used"],
        )
        return result

    def _global_search_query(self, message: str, language: str, correlation_id: str) -> str:
        """Translate a query into the configured language of global documents."""
        target_language = _language_key(settings.OPENSEARCH_GLOBAL_DOCUMENT_LANGUAGE)
        if _language_key(language) == target_language:
            return message

        system_prompt = (
            "Translate document-search queries into the requested target language. "
            "Preserve proper names, country names, organization names, acronyms, numbers, email addresses, and phone numbers. "
            "Return only the translated query without commentary or quotation marks."
        )
        user_prompt = f"Target language code: {target_language}\nQuery:\n{message}"
        try:
            response = get_aws_clients().bedrock_runtime.converse(
                modelId=settings.BEDROCK_MODEL_ARN,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                inferenceConfig={"maxTokens": settings.BEDROCK_GLOBAL_TRANSLATION_MAX_OUTPUT_TOKENS, "temperature": settings.BEDROCK_CLASSIFIER_TEMPERATURE},
            )
            translated = response["output"]["message"]["content"][0].get("text", "").strip()
        except (BotoCoreError, ClientError, KeyError, IndexError, TypeError):
            LOGGER.exception("opensearch_global_query_translation_failed", correlation_id=correlation_id)
            return message

        if not translated:
            return message
        LOGGER.info(
            "opensearch_global_query_translation_success",
            correlation_id=correlation_id,
            source_language=_language_key(language),
            target_language=target_language,
        )
        return translated.strip('"')

    def _build_search_plan(
        self,
        message: str,
        country: str,
        language: str,
        correlation_id: str,
    ) -> RetrievalQueryPlan:
        """Build runtime queries and select only relevant content scopes."""
        original = message.strip()
        if not original:
            return RetrievalQueryPlan([original], include_global_documents=False)
        return _planned_retrieval_plan(original, country, language, correlation_id)

    def _merge_hits(
        self,
        text_hits: list[dict[str, Any]],
        vector_hits: list[dict[str, Any]],
        message: str,
        *,
        ranking_queries: list[str] | None = None,
        prefer_outline: bool = False,
        target_country_names: set[str] | None = None,
    ) -> list[tuple[dict[str, Any], float]]:
        merged: dict[str, dict[str, Any]] = {}
        for hit in text_hits:
            row = _hit_to_row(hit)
            row_id = str(row["id"] or "")
            if not row_id:
                continue
            existing = merged.get(row_id)
            if existing is None or float(row.get("rank") or 0.0) > float(existing.get("rank") or 0.0):
                # Original and glossary searches may return the same section. Keep
                # the strongest text result instead of letting a later query erase it.
                merged[row_id] = row
        for hit in vector_hits:
            row = _hit_to_row(hit, score_weight=settings.OPENSEARCH_VECTOR_WEIGHT)
            if not row["id"]:
                continue
            existing = merged.get(row["id"])
            if existing is None:
                merged[row["id"]] = row
            else:
                existing["rank"] = float(existing.get("rank") or 0.0) + float(row.get("rank") or 0.0)

        self._normalize_opensearch_ranks(list(merged.values()))
        shared_evidence_text = [
            " ".join(
                [
                    str(row.get("section_title") or ""),
                    str(row.get("content") or "")[:500],
                ]
            )
            for row in list(merged.values())[: settings.OPENSEARCH_CANDIDATE_COUNT]
        ]
        shared_evidence_repair_queries = safe_typo_ranking_queries(
            message,
            shared_evidence_text,
        )
        shared_ranking_queries = list(
            dict.fromkeys([*(ranking_queries or []), *shared_evidence_repair_queries])
        )
        scored: list[tuple[dict[str, Any], float]] = []
        for row in merged.values():
            original_score = (
                _source_score(row, message)
                + _directory_record_country_score(message, row, target_country_names)
            )
            best_score = original_score
            ranking_query_used = message
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            evidence_repair_queries = safe_typo_ranking_queries(
                message,
                [
                    str(row.get("section_title") or ""),
                    str(row.get("content") or "")[:1500],
                    str(metadata.get("record_country") or ""),
                ],
            )
            candidate_ranking_queries = list(
                dict.fromkeys([*shared_ranking_queries, *evidence_repair_queries])
            )
            for ranking_query in candidate_ranking_queries:
                candidate_score = _source_score(row, ranking_query) + _directory_record_country_score(
                    ranking_query, row, target_country_names
                )
                if candidate_score > best_score:
                    best_score = candidate_score
                    ranking_query_used = ranking_query
            if prefer_outline and row.get("chunk_type") == "document_outline":
                best_score += 2.0
            row["original_question_score"] = round(original_score, 6)
            row["ranking_query_used"] = ranking_query_used
            row["typo_ranking_applied"] = ranking_query_used != message
            scored.append((row, round(best_score, 6)))
        return sorted(scored, key=lambda pair: pair[1], reverse=True)

    def _select_evidence_rows(
        self,
        message: str,
        rows: list[tuple[dict[str, Any], float]],
        correlation_id: str,
    ) -> list[tuple[dict[str, Any], float]]:
        """Optionally let a small model choose the best evidence from candidates."""
        if not settings.OPENSEARCH_EVIDENCE_SELECTOR_ENABLED or not rows:
            return rows

        candidate_limit = max(settings.OPENSEARCH_RESULT_COUNT, settings.OPENSEARCH_EVIDENCE_SELECTOR_CANDIDATE_COUNT)
        candidates = _selector_candidates(rows, candidate_limit)
        _record_rank_list_selector("requested", candidates=candidates)
        candidate_text = "\n\n".join(
            _selector_candidate_text(row, score, index)
            for index, (row, score) in enumerate(candidates, start=1)
        )
        system_prompt = (
            "You select evidence for ASK Vera. Do not answer the user's question. "
            "Choose the candidate approved-document sections that most directly support an answer. "
            "Treat harmless misspellings, omitted accents, and accidental character spacing as noisy user input; "
            "match the intended term when the candidate text makes that intent clear. "
            "The user question and a candidate document may use different languages; compare their meaning across languages. "
            "Use document type, record type, and record country metadata to distinguish office, staff, and policy evidence. "
            "When the user asks for an office, address, phone number, email address, website, or staff contact in a named place, "
            "prefer an office_directory candidate whose Record country matches that named place. "
            "The user's selected market is not necessarily the place they are asking about. "
            "Do not substitute a selected-market policy section that merely mentions generic customer care when a matching "
            "global office or staff record directly contains the requested contact information. "
            "Prefer the governing section for the user's exact intent over nearby sections that only mention similar words. "
            "When a return question says a product is unopened, unused, unsold, or salable and asks for a time window, "
            "prefer the FBO buy-back or unsold-salable-product clause over a general Retail/Preferred Customer satisfaction clause. "
            "List selected_ranks in order of relevance, most relevant first. "
            "Also set directly_answers_top_rank to true only if the FIRST candidate in selected_ranks explicitly "
            "states the specific fact, rule, amount, or mechanism the question asks about - not merely the same "
            "general topic. Check the specific scenario, not just the subject: a candidate about a different "
            "trigger, category, or type of action than the one asked about is NOT a direct answer, even if it "
            "shares the topic and vocabulary. For example, a clause about a member voluntarily choosing to leave "
            "does not directly answer a question about automatically losing status through inactivity; a clause "
            "about disputing a bonus or discount calculation does not directly answer a question about a damaged "
            "or incorrect physical order. When in doubt, set this to false - it is safer to say a candidate is "
            "only related than to claim it directly answers something it does not. "
            "Also rate top_rank_confidence from 0.0 to 1.0: how directly and completely the FIRST candidate in "
            "selected_ranks answers the user's question on its own, independent of how differently it is worded "
            "from the question - a paraphrased question and a formally-worded candidate can still deserve a high "
            "rating if the candidate's actual content states the fact, rule, or amount asked for. Base this on "
            "the candidate's content, not on how many of the question's words it shares. Use 0.85-1.0 only when "
            "directly_answers_top_rank is also true. Use 0.5-0.7 when it is clearly on-topic but only partially "
            "answers, needs minor inference, or addresses a related-but-different scenario. Use below 0.4 when it "
            "is only loosely related or you are guessing. "
        )
        if settings.OPENSEARCH_RETRIEVAL_HARDENING_ENABLED:
            system_prompt += (
                "A candidate is relevant only when its text contains the requested fact or a governing rule that directly answers it; "
                "sharing a product, company, person, rank, or country name is not enough. "
                "For a question about where or how to buy something, prefer a section that states a permitted purchase or sales channel, "
                "not a general company description or an unrelated product rule. "
                "For qualifications or requirements, prefer the clause that states how the exact named level is achieved, not a different "
                "type of manager or a later benefit that assumes qualification already happened. "
                "If none of the candidates directly supports an answer, mark relevant_evidence false and select no ranks. "
            )
        system_prompt += "Return only JSON."
        response_example = (
            '{"relevant_evidence":true,"selected_ranks":[1,2,3],"directly_answers_top_rank":true,'
            '"top_rank_confidence":0.9,"reason":"short reason"}'
            if settings.OPENSEARCH_RETRIEVAL_HARDENING_ENABLED
            else '{"selected_ranks":[1,2,3],"directly_answers_top_rank":true,"top_rank_confidence":0.9,"reason":"short reason"}'
        )
        user_prompt = (
            f"User question:\n{message}\n\n"
            f"Candidate sections:\n{candidate_text}\n\n"
            f"Select up to {settings.OPENSEARCH_RESULT_COUNT} candidate ranks. "
            f"Return JSON exactly like this: {response_example}."
        )
        try:
            response = get_aws_clients().bedrock_runtime.converse(
                modelId=settings.BEDROCK_MODEL_ARN,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                inferenceConfig={"maxTokens": settings.OPENSEARCH_EVIDENCE_SELECTOR_MAX_OUTPUT_TOKENS, "temperature": settings.BEDROCK_CLASSIFIER_TEMPERATURE},
            )
            text = response["output"]["message"]["content"][0].get("text", "")
            decision = _parse_selector_decision(text)
        except (BotoCoreError, ClientError, KeyError, IndexError, TypeError):
            LOGGER.exception("opensearch_evidence_selector_failed", correlation_id=correlation_id)
            _record_rank_list_selector("failed")
            return rows

        if decision is None:
            LOGGER.warning("opensearch_evidence_selector_invalid", correlation_id=correlation_id)
            _record_rank_list_selector("invalid")
            return rows
        ranks, relevant_evidence, top_rank_confidence, directly_answers_top_rank = decision
        _record_rank_list_selector("parsed", ranks=ranks, relevant_evidence=relevant_evidence)
        if (
            settings.OPENSEARCH_RETRIEVAL_HARDENING_ENABLED
            and relevant_evidence is False
            and not ranks
        ):
            LOGGER.info(
                "opensearch_evidence_selector_no_relevant_evidence",
                correlation_id=correlation_id,
                candidate_count=len(candidates),
            )
            return []

        selected: list[tuple[dict[str, Any], float]] = []
        selected_ids: set[str] = set()
        for position, rank in enumerate(ranks):
            if 1 <= rank <= len(candidates):
                candidate = candidates[rank - 1]
                row_id = str(candidate[0].get("id") or "")
                if row_id not in selected_ids:
                    candidate[0]["evidence_selector_selected"] = True
                    # Only the model's own first-ranked pick carries a
                    # confidence rating - it describes that specific
                    # candidate, not the whole selected set. The rating is
                    # only trusted to rescue a low lexical score when the
                    # model also explicitly confirmed this candidate
                    # directly answers the question, not merely that it's
                    # topically related - a plain 0-1 rating alone was not
                    # a reliable enough signal (it rated a voluntary-
                    # termination clause 0.75 confident for a question
                    # about automatic loss from inactivity).
                    if position == 0 and top_rank_confidence is not None and directly_answers_top_rank is True:
                        candidate[0]["evidence_selector_confidence"] = top_rank_confidence
                    if position == 0 and directly_answers_top_rank is False:
                        # The selector explicitly found the top pick topically
                        # relevant but not a direct answer (e.g. an office's
                        # directory record with no stated business hours for
                        # an hours question). Confidence blending deliberately
                        # never lets this lower the lexical score - a
                        # paraphrase can score this way on a genuinely correct
                        # pick too - but the prompt still needs the signal so
                        # generation doesn't present a field the source never
                        # actually states.
                        candidate[0]["evidence_selector_directly_answers"] = False
                    selected.append(candidate)
                    selected_ids.add(row_id)

        if not selected:
            LOGGER.info(
                "opensearch_evidence_selector_no_selection",
                correlation_id=correlation_id,
                candidate_count=len(candidates),
                ranks=ranks,
                relevant_evidence=relevant_evidence,
                top_rank_confidence=top_rank_confidence,
                directly_answers_top_rank=directly_answers_top_rank,
            )
            return rows

        remaining = [
            candidate
            for candidate in rows
            if str(candidate[0].get("id") or "") not in selected_ids
        ]
        LOGGER.info(
            "opensearch_evidence_selector_success",
            correlation_id=correlation_id,
            selected_count=len(selected),
            candidate_count=len(candidates),
            top_rank_confidence=top_rank_confidence,
            directly_answers_top_rank=directly_answers_top_rank,
        )
        return [*selected, *remaining]

    def _normalize_opensearch_ranks(self, rows: list[dict[str, Any]]) -> None:
        """Turn raw OpenSearch scores into a small ranking hint.

        OpenSearch BM25 scores can be 50-80+ for common policy words. The
        section scorer was designed around much smaller Postgres ranks, so raw
        OpenSearch scores can overwhelm intent signals like exact section title,
        rank requirement wording, and definition/onboarding intent.
        """
        if not rows:
            return
        raw_scores = [max(float(row.get("rank") or 0.0), 0.0) for row in rows]
        max_score = max(raw_scores)
        if max_score <= 0:
            return
        max_log = math.log1p(max_score)
        for row, raw_score in zip(rows, raw_scores, strict=False):
            row["rank"] = (math.log1p(raw_score) / max_log) * 1.25

    def _finalize_eligible_rows(
        self, rows: list[tuple[dict[str, Any], float]]
    ) -> list[tuple[dict[str, Any], float]]:
        """Apply the score floor, then optional per-parent diversity, before capping."""
        eligible = [(row, score) for row, score in rows if score >= settings.SECTION_RETRIEVAL_MIN_SCORE]
        if not settings.RETRIEVAL_PARENT_DIVERSITY_ENABLED or not eligible:
            return eligible

        from .experiments import diversify_by_parent

        score_by_identity = {id(row): score for row, score in eligible}
        diversified = diversify_by_parent(
            [row for row, _ in eligible],
            max_results=settings.OPENSEARCH_RESULT_COUNT,
            max_per_parent=settings.RETRIEVAL_MAX_RESULTS_PER_PARENT,
        )
        return [(row, score_by_identity[id(row)]) for row in diversified]

    def _document_from_row(self, row: dict[str, Any], score: float) -> RetrievedDocument:
        page = str(row.get("start_page") or "")
        end_page = row.get("end_page")
        if page and end_page and str(end_page) != page:
            page = f"{page}-{end_page}"
        source_uri = row.get("source_uri") or f"opensearch-section://{row.get('source_file', '')}/{row.get('section_id', '')}"
        if row.get("document_type") == "office_directory":
            title = f"{row.get('source_file', 'Directory')} - {row.get('section_title', 'Directory record')}"
        else:
            title = f"{row.get('source_file', 'Policy')} - Sec {row.get('section_id', '')}"
            if row.get("section_title"):
                title = f"{title}: {row['section_title']}"
        content = str(row.get("content") or "")
        metadata = dict(row.get("metadata") or {})
        if (
            row.get("document_type") == "office_directory"
            and metadata.get("directory_kind") != "international_sponsoring"
        ):
            metadata["directory_fields"] = parse_directory_fields(content)
        return RetrievedDocument(
            id=str(row.get("id") or ""),
            title=title,
            content=content,
            source=str(source_uri),
            excerpt=content[:300],
            page=page,
            document_version=str(row.get("document_version") or ""),
            country=str(row.get("country") or ""),
            language=str(row.get("language") or ""),
            score=score,
            metadata={
                **metadata,
                "ranking_query_used": row.get("ranking_query_used", ""),
                "typo_ranking_applied": bool(row.get("typo_ranking_applied")),
                "original_question_score": row.get("original_question_score"),
                "access_scope": row.get("access_scope", "country"),
                "document_type": row.get("document_type", ""),
                "section_id": row.get("section_id", ""),
                "section_title": row.get("section_title", ""),
                "parent_section_id": row.get("parent_section_id", ""),
                **({"parent_bound_child": True} if row.get("parent_bound_child") else {}),
            },
        )
