"""Bounded authority-aware scoring for already-filtered retrieval candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .classification import (
    QuestionClassification,
    SectionClassification,
    classify_question,
    classify_section,
    normalized_tags,
)


@dataclass(frozen=True)
class AuthorityAlignment:
    """Explainable authority score applied to one existing candidate."""

    score: float
    question: QuestionClassification
    section: SectionClassification
    entity_match: bool
    question_type_match: bool


_GOVERNING_QUESTION_TYPES = {
    "qualification",
    "eligibility",
    "restriction",
    "process",
    "pricing",
    "timing",
    "exception",
}


def _row_classification(row: dict[str, Any]) -> SectionClassification:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    fallback = classify_section(
        title=str(row.get("section_title") or ""),
        content=str(row.get("content") or ""),
        chunk_type=str(row.get("chunk_type") or "section"),
        document_type=str(row.get("document_type") or "policy"),
        metadata=metadata,
    )
    entities = normalized_tags(
        row.get("entity_tags") or metadata.get("entity_tags") or fallback.entities
    )
    question_types = normalized_tags(
        row.get("question_type_tags")
        or metadata.get("question_type_tags")
        or fallback.question_types
    )
    authority = str(
        row.get("section_authority")
        or metadata.get("section_authority")
        or fallback.authority
    ).strip().casefold()
    return SectionClassification(
        entities=entities,
        question_types=question_types,
        authority=authority,
    )


def authority_alignment(row: dict[str, Any], message: str) -> AuthorityAlignment:
    """Score authority/entity alignment without overriding retrieval relevance."""
    question = classify_question(message)
    section = _row_classification(row)
    question_entities = set(question.entities) - {"general"}
    section_entities = set(section.entities) - {"general"}
    entity_match = bool(question_entities and question_entities & section_entities)
    question_type_match = question.question_type in set(section.question_types)

    score = 0.0
    if entity_match:
        score += 0.75
    if question_type_match:
        score += 0.35

    if question.question_type == "definition":
        if section.authority == "definition":
            score += 1.1
        elif section.authority == "summary":
            score -= 0.2
    elif question.question_type == "contact":
        if section.authority == "directory":
            score += 1.25
        elif section.authority in {"definition", "summary"}:
            score -= 0.35
    elif question.question_type in _GOVERNING_QUESTION_TYPES:
        if section.authority == "governing":
            score += 1.25
        elif section.authority == "exception" and question.question_type == "exception":
            score += 1.15
        elif section.authority == "definition":
            score -= 0.55
        elif section.authority == "summary":
            score -= 0.3
    elif section.authority == "governing" and entity_match:
        score += 0.35

    # Authority cannot rescue an unrelated section. Apply authority-only boosts
    # only when either entity or question type aligns with the user question.
    if not entity_match and not question_type_match:
        score = min(score, 0.0)

    return AuthorityAlignment(
        score=round(max(min(score, 2.35), -0.75), 6),
        question=question,
        section=section,
        entity_match=entity_match,
        question_type_match=question_type_match,
    )
