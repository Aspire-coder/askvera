"""OpenSearch-backed section retrieval."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection
from opensearchpy.exceptions import OpenSearchException

from config import settings
from services.aws_clients import get_aws_clients
from services.embeddings import embed_text
from services.knowledge_generations import active_generation_ids
from services.market_config import find_market_mentions, get_countries, get_document_country_codes
from utils.logging import get_logger
from utils.opensearch_fields import exact_term_query, exact_terms_query

from .models import RetrievedDocument, RetrievalResult
from .providers import (
    RetrievalQueryPlan,
    _document_relevance,
    _planned_retrieval_plan,
    _planned_retrieval_queries,
)
from utils.directory_fields import parse_directory_fields
from .section_index import _character_overlap, _confidence_from_documents, _source_score
from .typo_safety import safe_typo_ranking_queries

LOGGER = get_logger("app.retrieval.opensearch_sections")

GLOBAL_DIRECTORY_DOCUMENT_TYPES = (
    "office_directory",
    "international_sponsoring_directory",
)
_DIRECTORY_DETAIL_RE = re.compile(
    r"\b(?:address|business\s+hours?|email|office|phone|telephone|website|contact)\b",
    re.IGNORECASE,
)


def _normalize_text(value: str) -> str:
    """Normalize text for glossary trigger checks."""
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    return " ".join("".join(character if character.isalnum() else " " for character in normalized).split())


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


def opensearch_index_exists(index_name: str) -> bool:
    """Return whether a named retrieval index exists without exposing client details."""
    normalized = str(index_name or "").strip()
    if not normalized:
        return False
    return bool(_client().indices.exists(index=normalized))


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
        if record_country in normalized_targets:
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


def _directory_target_country_names(message: str, selected_country: str) -> set[str]:
    """Return the named market(s) whose global directory record should lead."""
    mentioned_codes = find_market_mentions(message)
    if not mentioned_codes:
        normalized_message = _normalize_text(message)
        message_tokens = [token for token in normalized_message.split() if len(token) >= 4]
        for market in get_countries():
            market_name = _normalize_text(str(market.get("name") or ""))
            name_tokens = market_name.split()
            if len(name_tokens) != 1 or not market_name:
                continue
            if any(
                len(token) >= len(market_name) - 1
                and SequenceMatcher(None, token, market_name).ratio() >= 0.84
                for token in message_tokens
            ):
                mentioned_codes.add(str(market.get("code") or "").upper())
    if not mentioned_codes and not _DIRECTORY_DETAIL_RE.search(message or ""):
        return set()
    target_codes = mentioned_codes or {str(selected_country or "").upper()}
    return {
        str(country.get("name") or "")
        for country in get_countries()
        if str(country.get("code") or "").upper() in target_codes
    }


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
        "metadata": source.get("metadata", {}),
        "rank": float(hit.get("_score") or 0.0) * score_weight,
    }


def _selector_candidate_text(row: dict[str, Any], score: float, index: int) -> str:
    """Format one candidate for the evidence selector."""
    content = str(row.get("content") or "")
    metadata = dict(row.get("metadata") or {})
    return (
        f"Candidate {index}\n"
        f"Document type: {row.get('document_type', '')}\n"
        f"Access scope: {row.get('access_scope', 'country')}\n"
        f"Record type: {metadata.get('directory_section', '')}\n"
        f"Record country: {metadata.get('record_country', '')}\n"
        f"Section: {row.get('section_id', '')}\n"
        f"Title: {row.get('section_title', '')}\n"
        f"Current score: {score}\n"
        f"Text:\n{content[:1200]}"
    )


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


def _parse_selector_decision(text: str) -> tuple[list[int], bool | None] | None:
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
    return _parse_selector_ranks(json.dumps(payload)), relevant


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

    def retrieve(self, message: str, country: str, language: str, role: str, correlation_id: str) -> RetrievalResult:
        del role
        try:
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
            if (
                search_plan.conversation_intent != "knowledge"
                and search_plan.intent_confidence >= settings.BEDROCK_CONVERSATION_ROUTE_MIN_CONFIDENCE
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
            global_search_message = ""
            target_country_names = _directory_target_country_names(message, country)
            text_hits: list[dict[str, Any]] = []
            vector_hits: list[dict[str, Any]] = []
            explicit_section_id = _section_reference(message)
            if explicit_section_id:
                exact_response = client.search(
                    index=self.index_name,
                    body=_exact_section_query(explicit_section_id, country, language),
                )
                text_hits.extend(
                    {**hit, "_score": max(float(hit.get("_score") or 0.0), 100.0)}
                    for hit in exact_response.get("hits", {}).get("hits", [])
                )
            for index, search_message in enumerate(search_messages):
                weight = 1.0 if index == 0 else 0.88
                text_response = client.search(
                    index=self.index_name,
                    body=_text_query(search_message, country, language, scope="locale"),
                )
                vector_response = client.search(
                    index=self.index_name,
                    body=_vector_query(search_message, country, language, scope="locale"),
                )
                text_hits.extend(
                    {**hit, "_score": float(hit.get("_score") or 0.0) * weight}
                    for hit in text_response.get("hits", {}).get("hits", [])
                )
                vector_hits.extend(
                    {**hit, "_score": float(hit.get("_score") or 0.0) * weight}
                    for hit in vector_response.get("hits", {}).get("hits", [])
                )

            if search_plan.prefer_outline:
                outline_response = client.search(
                    index=self.index_name,
                    body=_outline_text_query(message, country, language),
                )
                text_hits.extend(outline_response.get("hits", {}).get("hits", []))

            if search_plan.include_global_documents:
                global_search_message = self._global_search_query(message, language, correlation_id)
                global_text_response = client.search(
                    index=self.index_name,
                    body=_directory_text_query(global_search_message, target_country_names),
                )
                global_vector_query = _vector_query(
                    global_search_message,
                    country,
                    language,
                    scope="global",
                )
                country_filter = _record_country_filter(target_country_names)
                if country_filter is not None:
                    global_vector_query["query"]["knn"]["embedding"]["filter"]["bool"]["filter"].append(
                        country_filter
                    )
                global_vector_response = client.search(
                    index=self.index_name,
                    body=global_vector_query,
                )
                text_hits.extend(global_text_response.get("hits", {}).get("hits", []))
                vector_hits.extend(global_vector_response.get("hits", {}).get("hits", []))
        except OpenSearchException:
            LOGGER.exception("opensearch_section_retrieval_failed", correlation_id=correlation_id)
            return RetrievalResult(documents=[], citations=[], confidence=0.0, metadata={"provider": "opensearch_section"})

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
        raw_rows = rows
        rows = self._select_evidence_rows(message, rows, correlation_id)
        selector_rejected = bool(raw_rows) and not rows and settings.OPENSEARCH_EVIDENCE_SELECTOR_ENABLED

        documents = [
            self._document_from_row(row, score)
            for row, score in rows
            if score >= settings.SECTION_RETRIEVAL_MIN_SCORE
        ][: settings.OPENSEARCH_RESULT_COUNT]
        selector_applied = bool(rows and rows[0][0].get("evidence_selector_selected"))
        max_local_relevance = _document_relevance(message, documents[0]) if documents else 0.0
        strong_local_match = bool(
            selector_applied
            and max_local_relevance >= settings.OPENSEARCH_SELECTOR_STRONG_MATCH_THRESHOLD
        )
        result = RetrievalResult(
            documents=documents,
            citations=[document.to_source() for document in documents],
            confidence=_confidence_from_documents(documents),
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
                "max_local_relevance": round(max_local_relevance, 6),
                "strong_local_match": strong_local_match,
                "candidate_sources": [
                    self._document_from_row(row, score).to_source()
                    for row, score in raw_rows[: settings.OPENSEARCH_CANDIDATE_COUNT]
                ],
            },
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
                inferenceConfig={"maxTokens": settings.BEDROCK_GLOBAL_TRANSLATION_MAX_OUTPUT_TOKENS},
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

    def _build_search_queries(
        self,
        message: str,
        country: str,
        language: str,
        correlation_id: str,
    ) -> list[str]:
        """Build runtime multilingual queries without country-specific aliases."""
        original = message.strip()
        if not original:
            return [original]
        return _planned_retrieval_queries(original, country, language, correlation_id)

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
            '{"relevant_evidence":true,"selected_ranks":[1,2,3],"reason":"short reason"}'
            if settings.OPENSEARCH_RETRIEVAL_HARDENING_ENABLED
            else '{"selected_ranks":[1,2,3],"reason":"short reason"}'
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
                inferenceConfig={"maxTokens": settings.OPENSEARCH_EVIDENCE_SELECTOR_MAX_OUTPUT_TOKENS},
            )
            text = response["output"]["message"]["content"][0].get("text", "")
            decision = _parse_selector_decision(text)
        except (BotoCoreError, ClientError, KeyError, IndexError, TypeError):
            LOGGER.exception("opensearch_evidence_selector_failed", correlation_id=correlation_id)
            return rows

        if decision is None:
            LOGGER.warning("opensearch_evidence_selector_invalid", correlation_id=correlation_id)
            return rows
        ranks, relevant_evidence = decision
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
        for rank in ranks:
            if 1 <= rank <= len(candidates):
                candidate = candidates[rank - 1]
                row_id = str(candidate[0].get("id") or "")
                if row_id not in selected_ids:
                    candidate[0]["evidence_selector_selected"] = True
                    selected.append(candidate)
                    selected_ids.add(row_id)

        if not selected:
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
            },
        )
