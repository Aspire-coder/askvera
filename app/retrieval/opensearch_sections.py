"""OpenSearch-backed section retrieval."""

from __future__ import annotations

import json
import math
from functools import lru_cache
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection
from opensearchpy.exceptions import OpenSearchException

from config import settings
from services.aws_clients import get_aws_clients
from services.embeddings import embed_text
from utils.logging import get_logger

from .models import RetrievedDocument, RetrievalResult
from .section_index import _confidence_from_documents, _source_score

LOGGER = get_logger("app.retrieval.opensearch_sections")


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
    """Use English policy sections as fallback until translated sections exist."""
    normalized = (language or "en").lower()
    if normalized == "en":
        return {"term": {"language": "en"}}
    return {"terms": {"language": [normalized, "en"]}}


def _text_query(message: str, country: str, language: str) -> dict[str, Any]:
    """Build a metadata-filtered BM25 query."""
    return {
        "size": settings.OPENSEARCH_CANDIDATE_COUNT,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"country": country}},
                    _language_filter(language),
                    {"term": {"status": "active"}},
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


def _vector_query(message: str, country: str, language: str) -> dict[str, Any]:
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
                                {"term": {"country": country}},
                                _language_filter(language),
                                {"term": {"status": "active"}},
                            ]
                        }
                    },
                }
            }
        },
    }


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
    return (
        f"Candidate {index}\n"
        f"Section: {row.get('section_id', '')}\n"
        f"Title: {row.get('section_title', '')}\n"
        f"Current score: {score}\n"
        f"Text:\n{content[:1200]}"
    )


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


def _parse_search_queries(text: str) -> list[str]:
    """Parse search queries from a compact JSON model response."""
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

    parsed: list[str] = []
    for query in payload.get("search_queries", []):
        normalized = str(query or "").strip()
        if normalized and normalized not in parsed:
            parsed.append(normalized)
    return parsed


class OpenSearchSectionProvider:
    """Retrieve approved policy sections from an OpenSearch section index."""

    def retrieve(self, message: str, country: str, language: str, role: str, correlation_id: str) -> RetrievalResult:
        del role
        try:
            client = _client()
            search_messages = self._rewrite_search_queries(message, correlation_id)
            text_hits: list[dict[str, Any]] = []
            vector_hits: list[dict[str, Any]] = []
            for index, search_message in enumerate(search_messages):
                weight = 1.0 if index == 0 else 0.88
                text_response = client.search(
                    index=settings.OPENSEARCH_INDEX,
                    body=_text_query(search_message, country, language),
                )
                vector_response = client.search(
                    index=settings.OPENSEARCH_INDEX,
                    body=_vector_query(search_message, country, language),
                )
                text_hits.extend(
                    {**hit, "_score": float(hit.get("_score") or 0.0) * weight}
                    for hit in text_response.get("hits", {}).get("hits", [])
                )
                vector_hits.extend(
                    {**hit, "_score": float(hit.get("_score") or 0.0) * weight}
                    for hit in vector_response.get("hits", {}).get("hits", [])
                )
        except OpenSearchException:
            LOGGER.exception("opensearch_section_retrieval_failed", correlation_id=correlation_id)
            return RetrievalResult(documents=[], citations=[], confidence=0.0, metadata={"provider": "opensearch_section"})

        rows = self._merge_hits(
            text_hits,
            vector_hits,
            message,
        )
        rows = self._select_evidence_rows(message, rows, correlation_id)

        documents = [
            self._document_from_row(row, score)
            for row, score in rows
            if score >= settings.SECTION_RETRIEVAL_MIN_SCORE
        ][: settings.OPENSEARCH_RESULT_COUNT]
        result = RetrievalResult(
            documents=documents,
            citations=[document.to_source() for document in documents],
            confidence=_confidence_from_documents(documents),
            metadata={
                "provider": "opensearch_section",
                "candidate_count": len(rows),
                "search_query_count": len(search_messages),
                "candidate_sources": [
                    self._document_from_row(row, score).to_source()
                    for row, score in rows[: settings.OPENSEARCH_CANDIDATE_COUNT]
                ],
            },
        )
        LOGGER.info(
            "opensearch_section_retrieval_success",
            correlation_id=correlation_id,
            country=country,
            language=language,
            source_count=len(result.sources),
            candidate_count=len(rows),
            confidence=result.confidence,
        )
        return result

    def _rewrite_search_queries(self, message: str, correlation_id: str) -> list[str]:
        """Optionally generate document-friendly search phrases for retrieval."""
        original = message.strip()
        if not settings.OPENSEARCH_QUERY_REWRITE_ENABLED or not original:
            return [original]

        system_prompt = (
            "You rewrite user questions into search queries for approved company policy documents. "
            "Do not answer the question. Keep queries short. Preserve the user's intent. "
            "Expand acronyms, informal names, legal/business wording, and translated wording into likely official policy terms. "
            "Do not invent specific section numbers or facts."
        )
        user_prompt = (
            f"User question:\n{original}\n\n"
            f"Return up to {settings.OPENSEARCH_QUERY_REWRITE_COUNT} search queries as JSON exactly like this: "
            "{\"search_queries\":[\"original or rewritten phrase\",\"another phrase\"]}."
        )
        try:
            response = get_aws_clients().bedrock_runtime.converse(
                modelId=settings.BEDROCK_MODEL_ARN,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
            )
            text = response["output"]["message"]["content"][0].get("text", "")
            rewritten = _parse_search_queries(text)
        except (BotoCoreError, ClientError, KeyError, IndexError, TypeError):
            LOGGER.exception("opensearch_query_rewrite_failed", correlation_id=correlation_id)
            return [original]

        search_queries = [original]
        for query in rewritten:
            if query not in search_queries:
                search_queries.append(query)
            if len(search_queries) >= settings.OPENSEARCH_QUERY_REWRITE_COUNT:
                break

        LOGGER.info(
            "opensearch_query_rewrite_success",
            correlation_id=correlation_id,
            query_count=len(search_queries),
        )
        return search_queries

    def _merge_hits(
        self,
        text_hits: list[dict[str, Any]],
        vector_hits: list[dict[str, Any]],
        message: str,
    ) -> list[tuple[dict[str, Any], float]]:
        merged: dict[str, dict[str, Any]] = {}
        for hit in text_hits:
            row = _hit_to_row(hit)
            if row["id"]:
                merged[row["id"]] = row
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
        scored = [(row, _source_score(row, message)) for row in merged.values()]
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
        candidates = rows[:candidate_limit]
        candidate_text = "\n\n".join(
            _selector_candidate_text(row, score, index)
            for index, (row, score) in enumerate(candidates, start=1)
        )
        system_prompt = (
            "You select evidence for ASK Vera. Do not answer the user's question. "
            "Choose the candidate policy sections that most directly support an answer. "
            "Prefer the governing section for the user's exact intent over nearby sections that only mention similar words. "
            "Return only JSON."
        )
        user_prompt = (
            f"User question:\n{message}\n\n"
            f"Candidate sections:\n{candidate_text}\n\n"
            f"Select up to {settings.OPENSEARCH_RESULT_COUNT} candidate ranks. "
            "Return JSON exactly like this: {\"selected_ranks\":[1,2,3],\"reason\":\"short reason\"}."
        )
        try:
            response = get_aws_clients().bedrock_runtime.converse(
                modelId=settings.BEDROCK_MODEL_ARN,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
            )
            text = response["output"]["message"]["content"][0].get("text", "")
            ranks = _parse_selector_ranks(text)
        except (BotoCoreError, ClientError, KeyError, IndexError, TypeError):
            LOGGER.exception("opensearch_evidence_selector_failed", correlation_id=correlation_id)
            return rows

        selected: list[tuple[dict[str, Any], float]] = []
        selected_ids: set[str] = set()
        for rank in ranks:
            if 1 <= rank <= len(candidates):
                candidate = candidates[rank - 1]
                row_id = str(candidate[0].get("id") or "")
                if row_id not in selected_ids:
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
        title = f"{row.get('source_file', 'Policy')} - Sec {row.get('section_id', '')}"
        if row.get("section_title"):
            title = f"{title}: {row['section_title']}"
        content = str(row.get("content") or "")
        return RetrievedDocument(
            id=str(row.get("id") or ""),
            title=title,
            content=content,
            source=str(source_uri),
            excerpt=content[:300],
            page=page,
            document_version="",
            country=str(row.get("country") or ""),
            language=str(row.get("language") or ""),
            score=score,
            metadata=dict(row.get("metadata") or {}),
        )
