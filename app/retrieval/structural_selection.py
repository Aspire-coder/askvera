"""Opt-in bridge from versioned retrieval documents to bound selection.

Not wired into production. Existing publication, governance, confidence and
answer-validation gates remain required. No model draft becomes a final answer.
"""

from dataclasses import dataclass, replace
import hashlib
from typing import Sequence
from urllib.parse import urlsplit

from app.retrieval.evidence_decision import EvidenceDecision, validate_decision
from app.retrieval.governing_rules import prioritize_activity_rule
from app.retrieval.models import RetrievedDocument
from app.retrieval.source_binding import EvidenceSource


@dataclass(frozen=True)
class StructuralSelection:
    documents: tuple[RetrievedDocument, ...]
    decision: EvidenceDecision


def document_sources(
    documents: Sequence[RetrievedDocument], *, country: str,
    active_ingestion_ids: set[str], allow_global_sponsoring: bool = False,
) -> tuple[EvidenceSource, ...]:
    """Require real identity and upstream publication IDs; add scope defense.

    active_ingestion_ids must come from an authorized publication lookup, not
    model output or the documents themselves. Language/expiry checks stay upstream.
    """
    if not isinstance(country, str) or not country.strip():
        raise ValueError("Missing selected market")
    sources = []
    seen = set()
    for document in documents:
        metadata = document.metadata
        scope = metadata.get("access_scope")
        if scope == "country":
            if document.country.upper() != country.upper():
                raise ValueError("Foreign country policy is not authorized")
            if metadata.get("document_type") != "policy":
                raise ValueError("Unsupported country document type")
        elif scope == "global":
            if not (allow_global_sponsoring and metadata.get("document_type") == "office_directory"
                    and metadata.get("directory_kind") == "international_sponsoring"):
                raise ValueError("Only authorized global sponsoring documents are supported")
        else:
            raise ValueError("Missing or unsupported document scope")
        generation = metadata.get("ingestion_id")
        if not isinstance(generation, str) or generation not in active_ingestion_ids:
            raise ValueError("Inactive or missing generation")
        if metadata.get("status") != "active":
            raise ValueError("Document is not active")
        content_hash = hashlib.sha256(document.content.encode("utf-8")).hexdigest()
        if metadata.get("content_hash") != content_hash:
            raise ValueError("Missing or mismatched content hash")
        if not document.id or document.id in seen:
            raise ValueError("Missing or duplicate document ID")
        seen.add(document.id)
        document_identity = metadata.get("logical_document_id")
        if not document_identity:
            uri = urlsplit(document.source)
            if uri.scheme != "s3" or not uri.netloc or not uri.path.strip("/") or uri.query or uri.fragment:
                raise ValueError("Missing stable document identity")
            document_identity = document.source
        sources.append(EvidenceSource(document_identity, generation,
                                      metadata.get("section_id"), document.country, document.content))
    if len({source.binding_id for source in sources}) != len(sources):
        raise ValueError("Duplicate source identity")
    return tuple(sources)


def select_bound_documents(
    payload: object, documents: Sequence[RetrievedDocument], *, question: str,
    country: str, language: str, active_ingestion_ids: set[str], allow_global_sponsoring: bool = False,
) -> StructuralSelection:
    """Accept full source IDs; preserve document scores and validation signals."""
    sources = document_sources(documents, country=country, active_ingestion_ids=active_ingestion_ids,
                               allow_global_sponsoring=allow_global_sponsoring)
    decision = validate_decision(payload, sources)
    lookup = {source.binding_id: document for source, document in zip(sources, documents)}
    quote_rows = []
    for index, quote in enumerate(decision.support):
        document = lookup[quote.source_id]
        quote_rows.append({"content": quote.quote, "section_title": document.metadata.get("section_title", ""),
                           "document_type": document.metadata.get("document_type"),
                           "access_scope": document.metadata.get("access_scope"), "quote_index": index})
    ordered = prioritize_activity_rule(question, quote_rows, language)
    decision = replace(decision, support=tuple(decision.support[row["quote_index"]] for row in ordered))
    return StructuralSelection(tuple(lookup[key] for key in decision.source_ids), decision)
