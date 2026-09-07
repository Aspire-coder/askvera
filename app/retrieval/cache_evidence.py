"""Fail closed for cached facts unless their evidence is still published."""

from dataclasses import asdict

from app.evidence import _has_current_locale_document
from app.retrieval.models import RetrievedDocument, RetrievalResult
from services.knowledge_generations import _active_generation_rows


def serialize_evidence(result: RetrievalResult) -> list[dict]:
    return [asdict(document) for document in result.documents]


def restore_evidence(value: object, country: str, language: str) -> RetrievalResult | None:
    if not isinstance(value, list) or not value:
        return None
    try:
        documents = [RetrievedDocument(**row) for row in value]
        if any(not isinstance(document.metadata, dict) for document in documents):
            return None
        if any(not _has_current_locale_document([document], country, language) for document in documents):
            return None
        # A fresh DB read is intentional: a per-worker TTL cannot enforce revocation.
        active = {str(row["active_ingestion_id"]) for row in _active_generation_rows(fresh=True)}
        if any(not document.metadata.get("ingestion_id")
               or document.metadata["ingestion_id"] not in active for document in documents):
            return None
    except (TypeError, ValueError, KeyError, AttributeError, RuntimeError):
        return None
    return RetrievalResult(documents=documents, citations=[doc.to_source() for doc in documents], confidence=1.0)
