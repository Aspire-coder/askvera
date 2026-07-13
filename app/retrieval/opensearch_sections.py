"""OpenSearch-backed section retrieval."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import boto3
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection
from opensearchpy.exceptions import OpenSearchException

from config import settings
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


def _text_query(message: str, country: str, language: str) -> dict[str, Any]:
    """Build a metadata-filtered BM25 query."""
    return {
        "size": settings.OPENSEARCH_CANDIDATE_COUNT,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"country": country}},
                    {"term": {"language": language}},
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
                                {"term": {"language": language}},
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
    row = {
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
    return row


class OpenSearchSectionProvider:
    """Retrieve approved policy sections from an OpenSearch section index."""

    def retrieve(self, message: str, country: str, language: str, role: str, correlation_id: str) -> RetrievalResult:
        del role
        try:
            client = _client()
            text_response = client.search(index=settings.OPENSEARCH_INDEX, body=_text_query(message, country, language))
            vector_response = client.search(
                index=settings.OPENSEARCH_INDEX,
                body=_vector_query(message, country, language),
            )
        except OpenSearchException:
            LOGGER.exception("opensearch_section_retrieval_failed", correlation_id=correlation_id)
            return RetrievalResult(documents=[], citations=[], confidence=0.0, metadata={"provider": "opensearch_section"})

        rows = self._merge_hits(
            text_response.get("hits", {}).get("hits", []),
            vector_response.get("hits", {}).get("hits", []),
            message,
        )
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

        scored = [(row, _source_score(row, message)) for row in merged.values()]
        return sorted(scored, key=lambda pair: pair[1], reverse=True)

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
