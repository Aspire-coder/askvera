"""Validate that numeric claims are grounded in retrieved source text."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.validation.models import ValidationContext, ValidationIssue, ValidationResult, ValidationSeverity


# Numbers are universal. The validator deliberately does not enumerate English
# units such as "months" or document-specific terms such as "Case Credits".
NUMERIC_CLAIM_PATTERN = re.compile(
    r"(?<![\w.])(?P<number>\d+(?:[.,]\d+)?(?:\s*(?:-|–|—)\s*\d+(?:[.,]\d+)?)?)(?![\w.])",
    re.UNICODE,
)


@dataclass(frozen=True)
class MeasurableClaim:
    """One numeric claim extracted from an answer."""

    text: str
    number: str
    start: int
    end: int
    sentence: str
    context: str


def _normalize(text: str) -> str:
    """Normalize text for tolerant, Unicode-safe source matching."""
    normalized = unicodedata.normalize("NFKC", text or "").casefold()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"\s*(?:-|–|—)\s*", "-", normalized)
    return normalized.strip()


def _number_variants(number: str) -> set[str]:
    """Return notation variants without assuming a language's range word."""
    return {_normalize(number)}


def _word_tokens(text: str) -> set[str]:
    """Return Unicode word tokens for local subject comparison."""
    return set(re.findall(r"[^\W\d_]{2,}", _normalize(text), flags=re.UNICODE))


def _sentence_for_claim(answer: str, start: int, end: int) -> str:
    """Return the sentence-like local answer window around a numeric claim."""
    left = max(answer.rfind(".", 0, start), answer.rfind("\n", 0, start), answer.rfind(":", 0, start))
    right_candidates = [position for position in (answer.find(".", end), answer.find("\n", end)) if position != -1]
    right = min(right_candidates) if right_candidates else len(answer)
    return answer[left + 1 : right].strip()


def _context_for_claim(answer: str, start: int, end: int, radius: int = 220) -> str:
    """Return nearby answer text that can include a named subject before the number."""
    return answer[max(0, start - radius) : min(len(answer), end + radius)].strip()


def _capitalized_entity_phrases(text: str) -> list[str]:
    """Extract title-like phrases without a language-specific alphabet or stopword list."""
    entities: list[str] = []
    current: list[str] = []
    for word in re.findall(r"[^\W\d_]+", text, flags=re.UNICODE):
        if word[:1].isupper():
            current.append(word)
        elif current:
            entities.append(" ".join(current))
            current = []
    if current:
        entities.append(" ".join(current))
    return entities


def _subject_token_sets(claim: MeasurableClaim) -> list[set[str]]:
    """Extract named subjects that connect a number to the policy topic."""
    before_claim = claim.sentence.split(claim.text, 1)[0] if claim.text in claim.sentence else claim.sentence
    context_before = claim.context.split(claim.text, 1)[0] if claim.text in claim.context else claim.context
    phrases = _capitalized_entity_phrases(before_claim) or _capitalized_entity_phrases(context_before)

    token_sets: list[set[str]] = []
    for phrase in phrases:
        words = re.findall(r"[^\W\d_]+", phrase, flags=re.UNICODE)
        # Include multi-word suffixes so a leading grammatical word never becomes
        # a hidden language dependency, for example "For Assistant Manager".
        for start in range(max(len(words) - 1, 1)):
            tokens = _word_tokens(" ".join(words[start:]))
            if len(tokens) >= 2 and tokens not in token_sets:
                token_sets.append(tokens)
    return token_sets


def _source_windows(source_text: str, number: str, radius: int = 260) -> list[str]:
    """Return clause-bounded source windows around the same number."""
    windows: list[str] = []
    pattern = re.compile(rf"(?<![\d.]){re.escape(number)}(?![\d.])")
    for match in pattern.finditer(source_text):
        index = match.start()
        left_boundary = max(source_text.rfind(delimiter, 0, index) for delimiter in (".", ";", "\n"))
        right_candidates = [
            position
            for position in (
                source_text.find(".", match.end()),
                source_text.find(";", match.end()),
                source_text.find("\n", match.end()),
            )
            if position != -1
        ]
        right_boundary = min(right_candidates) if right_candidates else len(source_text)
        window_start = max(left_boundary + 1 if left_boundary != -1 else 0, index - radius)
        window_end = min(right_boundary, match.end() + radius)
        windows.append(source_text[window_start:window_end])
    return windows


def _claim_is_supported(claim: MeasurableClaim, source_text: str) -> bool:
    """Return true only when the same number is linked to the same named topic."""
    subject_token_sets = _subject_token_sets(claim)
    for number in _number_variants(claim.number):
        for window in _source_windows(source_text, number):
            window_tokens = _word_tokens(window)
            if subject_token_sets and any(subject_tokens.issubset(window_tokens) for subject_tokens in subject_token_sets):
                return True

            # Some scripts do not capitalize names. In that case, retain a modest
            # lexical check instead of inventing a locale-specific entity grammar.
            if not subject_token_sets:
                context_overlap = _word_tokens(claim.context) & window_tokens
                if len(context_overlap) >= 2:
                    return True
    return False


def _structured_record_number_is_supported(claim: MeasurableClaim, source_text: str) -> bool:
    """Allow structured-record numbers despite harmless display formatting changes."""
    for number in _number_variants(claim.number):
        if _source_windows(source_text, number):
            return True

        # Office directories often store a phone number as one digit string while
        # an answer formats it with spaces, parentheses, or a country-code prefix.
        # Compare digits only in this structured-record path; policy rules retain
        # the stricter subject-aware matching above.
        claim_digits = "".join(character for character in number if character.isdigit())
        source_digits = "".join(character for character in source_text if character.isdigit())
        if claim_digits and claim_digits in source_digits:
            return True
    return False


def _extract_claims(answer: str) -> list[MeasurableClaim]:
    """Extract numeric claims from an answer without assuming unit vocabulary."""
    claims: list[MeasurableClaim] = []
    seen: set[str] = set()
    for match in NUMERIC_CLAIM_PATTERN.finditer(answer):
        claim = MeasurableClaim(
            text=match.group(0),
            number=match.group("number"),
            start=match.start(),
            end=match.end(),
            sentence=_sentence_for_claim(answer, match.start(), match.end()),
            context=_context_for_claim(answer, match.start(), match.end()),
        )
        key = _normalize(claim.text)
        if key not in seen:
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

        claims = _extract_claims(context.chat_response.answer or "")
        if not claims:
            return

        source_documents = [
            (document, _normalize(document.content))
            for document in retrieval_result.documents
            if document.content
        ]
        if not source_documents:
            return

        unsupported = [
            claim.text
            for claim in claims
            if not any(
                _claim_is_supported(claim, source_text)
                or (
                    document.metadata.get("directory_section") in {"office", "staff"}
                    and _structured_record_number_is_supported(claim, source_text)
                )
                for document, source_text in source_documents
            )
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
