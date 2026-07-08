"""Validate that measurable claims are grounded in retrieved source text."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.validation.models import ValidationContext, ValidationIssue, ValidationResult, ValidationSeverity


MEASURABLE_CLAIM_PATTERN = re.compile(
    r"""
    \b
    (?P<number>\d+(?:\.\d+)?(?:\s*(?:-|to)\s*\d+(?:\.\d+)?)?)
    \s*
    (?P<unit>
        open\s+group\s+case\s+credits?|
        case\s+credits?|
        ccs?|
        consecutive\s+months?|
        months?|
        days?|
        years?|
        weeks?|
        percent|
        percentage|
        %
    )
    (?=\W|$)
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass(frozen=True)
class MeasurableClaim:
    """One numeric claim extracted from an answer."""

    text: str
    number: str
    unit: str
    start: int
    end: int
    sentence: str
    context: str


def _normalize(text: str) -> str:
    """Normalize text for tolerant source matching."""
    normalized = text.lower()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"\s*-\s*", "-", normalized)
    return normalized.strip()


def _number_variants(number: str) -> set[str]:
    """Return normalized alternatives for equivalent numeric ranges."""
    normalized = _normalize(number)
    variants = {normalized}
    if " to " in normalized:
        variants.add(normalized.replace(" to ", "-"))
    if "-" in normalized:
        variants.add(normalized.replace("-", " to "))
    return variants


def _candidate_variants(claim: MeasurableClaim) -> set[str]:
    """Return normalized variants for the same measurable claim."""
    text = _normalize(claim.text)
    unit = _normalize(claim.unit)
    variants = {text}

    for number in _number_variants(claim.number):
        variants.add(f"{number} {unit}")

        if unit == "percent":
            variants.add(f"{number}%")
        if unit == "%":
            variants.add(f"{number} percent")
        if unit in {"cc", "ccs"}:
            variants.add(f"{number} case credit")
            variants.add(f"{number} case credits")
        if unit == "case credit":
            variants.add(f"{number} case credits")
        if unit == "case credits":
            variants.add(f"{number} case credit")
        if unit == "open group case credit":
            variants.add(f"{number} open group case credits")
        if unit == "open group case credits":
            variants.add(f"{number} open group case credit")

    return variants


LEADING_CAPITALIZED_STOPWORDS = {
    "A",
    "An",
    "And",
    "As",
    "At",
    "For",
    "If",
    "In",
    "On",
    "Once",
    "Per",
    "The",
    "Then",
    "This",
    "To",
    "When",
    "You",
}


def _sentence_for_claim(answer: str, start: int, end: int) -> str:
    """Return the sentence-like local answer window around a measurable claim."""
    left = max(answer.rfind(".", 0, start), answer.rfind("\n", 0, start), answer.rfind(":", 0, start))
    right_candidates = [position for position in (answer.find(".", end), answer.find("\n", end)) if position != -1]
    right = min(right_candidates) if right_candidates else len(answer)
    return answer[left + 1 : right].strip()


def _context_for_claim(answer: str, start: int, end: int, radius: int = 220) -> str:
    """Return a nearby answer window that can include a subject named earlier."""
    return answer[max(0, start - radius) : min(len(answer), end + radius)].strip()


def _capitalized_entity_phrases(text: str) -> list[str]:
    """Extract generic entity-like phrases from original-case text."""
    capitalized_phrases = re.findall(
        r"\b(?:[A-Z][a-z]+|[A-Z]{2,})(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,}))*\b",
        text,
    )
    entities: list[str] = []
    for phrase in capitalized_phrases:
        words = phrase.split()
        while words and words[0] in LEADING_CAPITALIZED_STOPWORDS:
            words = words[1:]
        if words:
            entities.append(" ".join(words))
    return entities


def _subject_token_sets(claim: MeasurableClaim) -> list[set[str]]:
    """Extract possible entity subjects that connect the number to a thing."""
    before_claim = claim.sentence.split(claim.text, 1)[0] if claim.text in claim.sentence else claim.sentence
    phrases = [phrase for phrase in _capitalized_entity_phrases(before_claim) if len(phrase.split()) > 1]
    if not phrases:
        context_before_claim = claim.context.split(claim.text, 1)[0] if claim.text in claim.context else claim.context
        phrases = [phrase for phrase in _capitalized_entity_phrases(context_before_claim) if len(phrase.split()) > 1]
    if not phrases:
        phrases = _capitalized_entity_phrases(before_claim)
    if not phrases:
        context_before_claim = claim.context.split(claim.text, 1)[0] if claim.text in claim.context else claim.context
        phrases = _capitalized_entity_phrases(context_before_claim)

    token_sets: list[set[str]] = []
    for phrase in phrases:
        tokens = set(re.findall(r"[a-z][a-z]+", _normalize(phrase)))
        if tokens and tokens not in token_sets:
            token_sets.append(tokens)
    return token_sets


def _source_windows(source_text: str, variant: str, radius: int = 180) -> list[str]:
    """Return local source windows around a grounded claim candidate."""
    windows: list[str] = []
    start = 0
    while True:
        index = source_text.find(variant, start)
        if index == -1:
            break

        left_candidates = [source_text.rfind(delimiter, 0, index) for delimiter in (".", ";")]
        right_candidates = [
            position for position in (source_text.find(".", index + len(variant)), source_text.find(";", index + len(variant))) if position != -1
        ]
        left = max(left_candidates)
        right = min(right_candidates) if right_candidates else -1

        window_start = left + 1 if left != -1 else max(0, index - radius)
        window_end = right if right != -1 else min(len(source_text), index + len(variant) + radius)
        windows.append(source_text[window_start:window_end])
        start = index + max(len(variant), 1)
    return windows


def _claim_is_supported(claim: MeasurableClaim, source_text: str) -> bool:
    """Return true when the claim and its nearby subject appear in source context."""
    subject_token_sets = _subject_token_sets(claim)
    for variant in _candidate_variants(claim):
        if not variant:
            continue
        for window in _source_windows(source_text, variant):
            window_tokens = set(re.findall(r"[a-z][a-z]+", window))
            if not subject_token_sets:
                return True
            if any(subject_tokens.issubset(window_tokens) for subject_tokens in subject_token_sets):
                return True
    return False


def _extract_claims(answer: str) -> list[MeasurableClaim]:
    """Extract measurable claims from the answer."""
    claims: list[MeasurableClaim] = []
    seen: set[str] = set()
    for match in MEASURABLE_CLAIM_PATTERN.finditer(answer):
        claim = MeasurableClaim(
            text=match.group(0),
            number=match.group("number"),
            unit=match.group("unit"),
            start=match.start(),
            end=match.end(),
            sentence=_sentence_for_claim(answer, match.start(), match.end()),
            context=_context_for_claim(answer, match.start(), match.end()),
        )
        key = _normalize(claim.text)
        if key in seen:
            continue
        seen.add(key)
        claims.append(claim)
    return claims


class NumericGroundingValidator:
    """Block measurable claims that are absent from retrieved context."""

    name = "numeric_grounding"

    def validate(self, context: ValidationContext, result: ValidationResult) -> None:
        retrieval_result = context.retrieval_result
        if retrieval_result is None or not retrieval_result.documents:
            return

        answer = context.chat_response.answer or ""
        claims = _extract_claims(answer)
        if not claims:
            return

        source_text = _normalize("\n".join(document.content for document in retrieval_result.documents if document.content))
        if not source_text:
            return

        unsupported = [
            claim.text
            for claim in claims
            if not _claim_is_supported(claim, source_text)
        ]
        if not unsupported:
            return

        result.add_issue(
            ValidationIssue(
                code="NUMERIC_CLAIM_UNGROUNDED",
                message="One or more measurable claims in the answer were not found in the retrieved source text: "
                + "; ".join(unsupported),
                severity=ValidationSeverity.CRITICAL,
                field="answer",
            )
        )
