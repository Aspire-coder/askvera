"""Explainable confidence scoring based on approved evidence signals."""

from __future__ import annotations

from dataclasses import dataclass

from .authority_ranking import authority_alignment
from .models import RetrievedDocument


@dataclass(frozen=True)
class ConfidenceAssessment:
    """Candidate confidence and the bounded signals that produced it."""

    confidence: float
    signals: dict[str, float | bool | str]


def _document_row(document: RetrievedDocument) -> dict[str, object]:
    metadata = document.metadata or {}
    return {
        "section_title": metadata.get("section_title") or document.title,
        "content": document.content,
        "chunk_type": metadata.get("chunk_type") or "section",
        "document_type": metadata.get("document_type") or "policy",
        "entity_tags": metadata.get("entity_tags") or [],
        "question_type_tags": metadata.get("question_type_tags") or [],
        "section_authority": metadata.get("section_authority") or "",
        "metadata": metadata,
    }


def signal_confidence(
    documents: list[RetrievedDocument],
    message: str,
    country: str,
    language: str,
) -> ConfidenceAssessment:
    """Assess evidence without changing the established approval threshold."""
    if not documents:
        return ConfidenceAssessment(confidence=0.0, signals={"has_evidence": False})

    top = documents[0]
    alignment = authority_alignment(_document_row(top), message)
    metadata = top.metadata or {}
    access_scope = str(metadata.get("access_scope") or "country").casefold()
    document_country = str(top.country or metadata.get("country") or "").upper()
    document_language = str(top.language or metadata.get("language") or "").casefold()
    requested_country = str(country or "").upper()
    requested_language = str(language or "").casefold().split("-", 1)[0]
    locale_country_match = access_scope == "global" or document_country == requested_country
    locale_language_match = access_scope == "global" or document_language.split("-", 1)[0] == requested_language

    raw_score = max(float(top.score or 0.0), 0.0)
    score_signal = min(raw_score / 6.0, 1.0) * 0.22
    entity_signal = 0.16 if alignment.entity_match else 0.0
    question_type_signal = 0.10 if alignment.question_type_match else 0.0
    authority_signal = 0.0
    if alignment.question.question_type == "definition" and alignment.section.authority == "definition":
        authority_signal = 0.16
    elif alignment.question.question_type == "contact" and alignment.section.authority == "directory":
        authority_signal = 0.16
    elif alignment.question.question_type in {
        "qualification", "eligibility", "restriction", "process", "pricing", "timing", "exception",
    } and alignment.section.authority in {"governing", "exception"}:
        authority_signal = 0.16
    elif alignment.entity_match and alignment.section.authority == "governing":
        authority_signal = 0.08

    locale_signal = 0.0
    if locale_country_match:
        locale_signal += 0.06
    if locale_language_match:
        locale_signal += 0.04

    selected_signal = 0.04 if metadata.get("evidence_selector_selected") else 0.0
    parent_ids = {
        str(document.metadata.get("parent_section_id") or document.metadata.get("section_id") or document.id)
        for document in documents[:3]
    }
    source_files = {
        str(document.metadata.get("source_file") or document.source)
        for document in documents[:3]
    }
    corroboration_signal = 0.06 if len(parent_ids) > 1 or len(source_files) > 1 else 0.0

    penalty = 0.0
    if not locale_country_match:
        penalty += 0.35
    if not locale_language_match:
        penalty += 0.25
    if not alignment.entity_match and not alignment.question_type_match:
        penalty += 0.18
    if alignment.section.authority == "summary":
        penalty += 0.08

    confidence = (
        0.14
        + score_signal
        + entity_signal
        + question_type_signal
        + authority_signal
        + locale_signal
        + selected_signal
        + corroboration_signal
        - penalty
    )
    confidence = round(max(0.0, min(confidence, 0.95)), 3)
    return ConfidenceAssessment(
        confidence=confidence,
        signals={
            "has_evidence": True,
            "raw_score": round(raw_score, 6),
            "score_signal": round(score_signal, 6),
            "entity_match": alignment.entity_match,
            "question_type_match": alignment.question_type_match,
            "section_authority": alignment.section.authority,
            "authority_signal": authority_signal,
            "locale_country_match": locale_country_match,
            "locale_language_match": locale_language_match,
            "selector_selected": bool(metadata.get("evidence_selector_selected")),
            "corroboration_signal": corroboration_signal,
            "penalty": round(penalty, 6),
        },
    )
