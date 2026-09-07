"""Validate that numeric claims are grounded in retrieved source text."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.validation.models import ValidationContext, ValidationIssue, ValidationResult, ValidationSeverity
from utils.redaction import PHONE_RE


# Numbers are universal. The validator deliberately does not enumerate English
# units such as "months" or document-specific terms such as "Case Credits".
NUMERIC_CLAIM_PATTERN = re.compile(
    r"(?<![\w.])(?P<number>\d+(?:[.,]\d+)?(?:\s*(?:-|\u2013|\u2014)\s*\d+(?:[.,]\d+)?)?)(?!\w|\.\d)",
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
    prefix: str


def _normalize(text: str) -> str:
    """Normalize text for tolerant, Unicode-safe source matching."""
    normalized = unicodedata.normalize("NFKC", text or "").casefold()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"\s*(?:-|\u2013|\u2014)\s*", "-", normalized)
    return normalized.strip()


def _number_variants(number: str) -> set[str]:
    """Return safe decimal notation variants without changing numeric value."""
    normalized = _normalize(number)
    variants = {normalized}
    # A one- or two-digit fractional part is unambiguously decimal in the
    # policy data we validate. Treat comma and point notation as equivalent so
    # an English answer can cite a source that uses continental formatting.
    decimal_match = re.fullmatch(r"(?P<whole>\d+)(?P<separator>[.,])(?P<fraction>\d{1,2})", normalized)
    if decimal_match:
        other_separator = "," if decimal_match.group("separator") == "." else "."
        variants.add(
            f"{decimal_match.group('whole')}{other_separator}{decimal_match.group('fraction')}"
        )
    return variants


def _word_tokens(text: str) -> set[str]:
    """Return Unicode word tokens for local subject comparison."""
    return set(re.findall(r"[^\W\d_]{2,}", _normalize(text), flags=re.UNICODE))


def _tokens_match(subject_token: str, source_token: str) -> bool:
    """Match exact words or conservative grammatical variants."""
    if subject_token == source_token:
        return True

    shorter_length = min(len(subject_token), len(source_token))
    if shorter_length < 6:
        return False

    common_prefix_length = 0
    for subject_character, source_character in zip(subject_token, source_token):
        if subject_character != source_character:
            break
        common_prefix_length += 1

    return common_prefix_length >= max(6, int(shorter_length * 0.7))


def _subject_matches_window(subject_tokens: set[str], window_tokens: set[str]) -> bool:
    """Return true when every subject word has an exact or inflected match."""
    return all(
        any(_tokens_match(subject_token, window_token) for window_token in window_tokens)
        for subject_token in subject_tokens
    )


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
    # Preserve this occurrence's position: splitting on the numeric text links
    # repeated values to the first subject instead of the current claim.
    phrases = _capitalized_entity_phrases(claim.prefix)
    phrases = [phrase for phrase in phrases if len(_word_tokens(phrase)) >= 2][-1:]

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
    pattern = re.compile(rf"(?<![\d.]){re.escape(number)}(?!\d|\.\d)")
    for match in pattern.finditer(source_text):
        index = match.start()
        # PDF extraction inserts line breaks for visual wrapping and numbered
        # lists. Keep those lines attached to the heading that names the rule.
        left_boundary = max(source_text.rfind(delimiter, 0, index) for delimiter in (".", ";"))
        right_candidates = [
            position
            for position in (
                source_text.find(".", match.end()),
                source_text.find(";", match.end()),
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
            if subject_token_sets and any(
                _subject_matches_window(subject_tokens, window_tokens) for subject_tokens in subject_token_sets
            ):
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


def _phone_matches(text: str) -> list[re.Match[str]]:
    vanity = re.compile(r"(?<!\w)(?:\d{1,4}[- ]\s*){2,3}[a-z]{3,10}\s*\(\d{3,6}\)", re.I)
    vanity_matches = list(vanity.finditer(text))
    return [match for match in [*vanity_matches, *PHONE_RE.finditer(text)]
            if 7 <= sum(char.isdigit() for char in match.group()) <= 15
            and not any(other.start() <= match.start() and match.end() <= other.end()
                        for other in vanity_matches if other is not match)]


def _extract_claims(answer: str) -> list[MeasurableClaim]:
    """Extract numeric claims from an answer without assuming unit vocabulary."""
    claims: list[MeasurableClaim] = []
    phones = _phone_matches(answer)
    numbers = [match for match in NUMERIC_CLAIM_PATTERN.finditer(answer)
               if not any(phone.start() <= match.start() and match.end() <= phone.end() for phone in phones)]
    for match in sorted([*phones, *numbers], key=lambda item: item.start()):
        if _is_structural_reference(answer, match.start(), match.end()):
            continue
        claim = MeasurableClaim(
            text=match.group(0),
            number=match.group(0),
            start=match.start(),
            end=match.end(),
            sentence=_sentence_for_claim(answer, match.start(), match.end()),
            context=_context_for_claim(answer, match.start(), match.end()),
            prefix=answer[max(0, match.start() - 220):match.start()],
        )
        claims.append(claim)
    return claims


def _is_structural_reference(answer: str, start: int, end: int) -> bool:
    """Ignore presentation numbers that are not measurable factual claims."""
    before = answer[start - 1 : start] if start else ""
    after = answer[end : end + 1]
    if before in {"[", "("} and after in {"]", ")"}:
        return True

    line_start = answer.rfind("\n", 0, start) + 1
    line_prefix = answer[line_start:start]
    if not line_prefix.strip() and after in {")", ":"}:
        return True
    return False


def _grounded_phone_spans(answer: str, source_texts: list[str]) -> list[tuple[int, int]]:
    """Compare whole contact values, never digits concatenated across a document.

    A source contact label is required. Answer wording may be translated; numeric
    policy rules elsewhere still go through the existing subject-binding check.
    """
    label = re.compile(r"\b(?:telephone|phone|fax|call|customer care|toll.free)\b", re.I)

    def key(value: str) -> str:
        return re.sub(r"[\s()+.-]", "", value).casefold()

    approved = {
        key(match.group())
        for source in source_texts
        for match in _phone_matches(source)
        if label.search(source[max(0, match.start() - 65):match.start()])
    }
    return [(match.start(), match.end()) for match in _phone_matches(answer) if key(match.group()) in approved]


def unsupported_numeric_claims(answer: str, source_documents: list[object]) -> list[MeasurableClaim]:
    """Return factual numeric claims that no retrieved source supports."""
    source_texts = [
        _normalize(str(getattr(document, "content", "") or ""))
        for document in source_documents
        if getattr(document, "content", "")
    ]
    if not source_texts:
        return []
    phone_spans = _grounded_phone_spans(answer, source_texts)
    return [
        claim
        for claim in _extract_claims(answer)
        if not any(start <= claim.start and claim.end <= end for start, end in phone_spans)
        if not any(_claim_is_supported(claim, source_text) for source_text in source_texts)
    ]


def remove_unsupported_numeric_sentences(answer: str, source_documents: list[object]) -> tuple[str, list[str]]:
    """Remove only sentences containing unsupported numbers, preserving grounded text."""
    unsupported = unsupported_numeric_claims(answer, source_documents)
    if not unsupported:
        return answer, []

    spans: list[tuple[int, int]] = []
    # Decimal/time separators are not sentence endings. A bare period search
    # left fragments such as "00 pm" after deleting a sentence with 09.00-17.00.
    abbreviations = list(re.finditer(r"\b(?:[^\W\d_]\.){2,}", answer))
    boundaries = [match for match in re.finditer(r"[.!?](?=\s|$)|\n", answer)
                  if not any(abbreviation.start() <= match.start() < abbreviation.end()
                             for abbreviation in abbreviations)]
    for claim in unsupported:
        left = max((match.end() for match in boundaries if match.end() <= claim.start), default=0)
        right = next((match.end() for match in boundaries if match.start() >= claim.end), len(answer))
        spans.append((left, right))

    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    repaired = answer
    for start, end in reversed(merged):
        repaired = repaired[:start] + repaired[end:]
    repaired = re.sub(r"[ \t]+\n", "\n", repaired)
    repaired = re.sub(r"\n{3,}", "\n\n", repaired).strip()
    return repaired, [claim.text for claim in unsupported]


class NumericGroundingValidator:
    """Block measurable claims that are absent from retrieved context."""

    name = "numeric_grounding"

    def validate(self, context: ValidationContext, result: ValidationResult) -> None:
        retrieval_result = context.retrieval_result
        if retrieval_result is None or not retrieval_result.documents:
            return

        answer = context.chat_response.answer or ""
        source_documents = [
            (document, _normalize(document.content))
            for document in retrieval_result.documents
            if document.content
        ]
        if not source_documents:
            return

        # unsupported_numeric_claims already excludes source-grounded contact
        # values. The remaining check rescues numbers that appear only inside a
        # structured office/staff directory record rather than in running text.
        unsupported = [
            claim.text
            for claim in unsupported_numeric_claims(answer, retrieval_result.documents)
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
