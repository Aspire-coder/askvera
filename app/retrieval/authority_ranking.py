"""Bounded authority-aware scoring for already-filtered retrieval candidates."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
import unicodedata

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
    entity_match_count: int
    entity_coverage: float
    question_type_match: bool
    directory_country_match: bool


_GOVERNING_QUESTION_TYPES = {
    "qualification",
    "eligibility",
    "restriction",
    "process",
    "pricing",
    "timing",
    "exception",
}


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "").casefold()
    normalized = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return " ".join(normalized.split())


def _directory_country_matches(
    row: dict[str, Any],
    message: str,
    section: SectionClassification,
) -> bool:
    """Recognize an explicitly requested country directory record."""
    if section.authority != "directory":
        return False
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    record_country = _normalize_text(str(metadata.get("record_country") or ""))
    normalized_message = _normalize_text(message)
    return bool(
        record_country
        and re.search(rf"(?<!\w){re.escape(record_country)}(?!\w)", normalized_message)
    )


def _authority_score(
    question_type: str,
    authority: str,
    entity_match: bool,
    directory_country_match: bool,
) -> float:
    """Return the authority-only contribution for an aligned candidate."""
    if directory_country_match:
        return 1.25
    if question_type == "definition":
        return {"definition": 1.1, "summary": -0.2}.get(authority, 0.0)
    if question_type == "contact":
        if authority == "directory":
            return 1.25
        return -0.35 if authority in {"definition", "summary"} else 0.0
    if question_type in _GOVERNING_QUESTION_TYPES:
        if authority == "governing":
            return 1.25
        if authority == "exception" and question_type == "exception":
            return 1.15
        return {"definition": -0.55, "summary": -0.3}.get(authority, 0.0)
    if authority == "governing" and entity_match:
        return 0.35
    return 0.0


def _row_classification(row: dict[str, Any]) -> SectionClassification:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    fallback = classify_section(
        title=str(row.get("section_title") or ""),
        content=str(row.get("content") or ""),
        chunk_type=str(row.get("chunk_type") or "section"),
        document_type=str(row.get("document_type") or "policy"),
        metadata=metadata,
    )
    # Stored tags remain authoritative inputs, but classifiers can gain new,
    # backward-compatible concepts without requiring an immediate reindex.
    # Merging avoids silently discarding either source of reviewed metadata.
    stored_entities = normalized_tags(
        row.get("entity_tags") or metadata.get("entity_tags") or ()
    )
    entities = normalized_tags((*stored_entities, *fallback.entities))
    stored_question_types = normalized_tags(
        row.get("question_type_tags") or metadata.get("question_type_tags") or ()
    )
    question_types = normalized_tags(
        (*stored_question_types, *fallback.question_types)
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
    matched_entities = question_entities & section_entities
    entity_match_count = len(matched_entities)
    entity_match = bool(question_entities and matched_entities)
    entity_coverage = (
        entity_match_count / len(question_entities) if question_entities else 0.0
    )
    question_type_match = question.question_type in set(section.question_types)
    directory_country_match = _directory_country_matches(row, message, section)

    # Reward sections that match more of a compound concept, not merely one
    # broad token. The bounded increment distinguishes, for example, a generic
    # returns passage from an unsold/salable inventory rule when both are valid.
    entity_specificity = min(max(entity_match_count - 1, 0), 2) * 0.15
    score = (0.75 if entity_match else 0.0) + entity_specificity + (
        0.35 if question_type_match else 0.0
    )
    score += _authority_score(
        question.question_type,
        section.authority,
        entity_match,
        directory_country_match,
    )

    # Authority cannot rescue an unrelated section. Apply authority-only boosts
    # only when either entity or question type aligns with the user question.
    if not entity_match and not question_type_match and not directory_country_match:
        score = min(score, 0.0)

    return AuthorityAlignment(
        score=round(max(min(score, 2.65), -0.75), 6),
        question=question,
        section=section,
        entity_match=entity_match,
        entity_match_count=entity_match_count,
        entity_coverage=round(entity_coverage, 6),
        question_type_match=question_type_match,
        directory_country_match=directory_country_match,
    )
