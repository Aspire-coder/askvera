"""Optional Bedrock reranking for already-retrieved document candidates."""

from __future__ import annotations

from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from config import settings
from services.aws_clients import get_aws_clients
from utils.logging import get_logger

LOGGER = get_logger("app.retrieval.bedrock_reranker")


def _candidate_text(row: dict[str, Any]) -> str:
    """Build a compact, metadata-aware representation for the rerank model."""
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    parts = [
        f"Document type: {row.get('document_type', '')}",
        f"Country: {row.get('country', '')}",
        f"Language: {row.get('language', '')}",
        f"Record country: {metadata.get('record_country', '')}",
        f"Section: {row.get('section_id', '')}",
        f"Title: {row.get('section_title', '')}",
        str(row.get("content") or row.get("search_text") or ""),
    ]
    return "\n".join(part for part in parts if not part.endswith(": "))


def rerank_rows(
    query: str,
    rows: list[tuple[dict[str, Any], float]],
    *,
    correlation_id: str,
) -> list[tuple[dict[str, Any], float]]:
    """Rerank a bounded candidate set, preserving the original order on failure."""
    if not rows:
        return rows

    candidate_count = max(
        settings.OPENSEARCH_RESULT_COUNT,
        settings.RETRIEVAL_VNEXT_RERANK_CANDIDATE_COUNT,
    )
    candidates = rows[:candidate_count]
    sources = [
        {
            "type": "INLINE",
            "inlineDocumentSource": {
                "type": "TEXT",
                "textDocument": {"text": _candidate_text(row)},
            },
        }
        for row, _score in candidates
    ]

    try:
        response = get_aws_clients().bedrock_agent_runtime.rerank(
            queries=[{"type": "TEXT", "textQuery": {"text": query}}],
            sources=sources,
            rerankingConfiguration={
                "type": "BEDROCK_RERANKING_MODEL",
                "bedrockRerankingConfiguration": {
                    "modelConfiguration": {
                        "modelArn": settings.RETRIEVAL_VNEXT_RERANK_MODEL_ARN,
                    },
                    "numberOfResults": min(
                        len(candidates),
                        max(settings.OPENSEARCH_RESULT_COUNT, settings.RETRIEVAL_VNEXT_RERANK_RESULT_COUNT),
                    ),
                },
            },
        )
    except (BotoCoreError, ClientError, KeyError, TypeError, ValueError):
        LOGGER.exception("bedrock_rerank_failed", correlation_id=correlation_id)
        return rows

    selected: list[tuple[dict[str, Any], float]] = []
    selected_ids: set[str] = set()
    for result in response.get("results", []):
        index = result.get("index")
        if not isinstance(index, int) or not 0 <= index < len(candidates):
            continue
        candidate = candidates[index]
        row_id = str(candidate[0].get("id") or index)
        if row_id in selected_ids:
            continue
        selected.append(candidate)
        selected_ids.add(row_id)

    if not selected:
        LOGGER.warning("bedrock_rerank_empty", correlation_id=correlation_id)
        return rows

    remaining = [
        candidate
        for index, candidate in enumerate(rows)
        if str(candidate[0].get("id") or index) not in selected_ids
    ]
    LOGGER.info(
        "bedrock_rerank_success",
        correlation_id=correlation_id,
        candidate_count=len(candidates),
        selected_count=len(selected),
    )
    return [*selected, *remaining]
