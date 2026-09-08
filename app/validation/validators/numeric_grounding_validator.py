"""Validate that numeric claims are grounded in retrieved source text."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.validation.models import ValidationContext, ValidationIssue, ValidationResult, ValidationSeverity
from utils.redaction import PHONE_RE


# Numbers are universal. The validator deliberately does not enumerate English
# units such as "months" or document-specific terms such as "Case Credits".
# A thousands group belongs to the number in front of it. Without this,
# "7 800DZD" was read as the claim "7", which then matched nothing once the
# source had been canonicalised to "7800dzd", and the sentence stating
# Algeria's minimum order was deleted.
_GROUPED_NUMBER = r"\d+(?:[ \u00a0\u202f]\d{3}(?!\d))*(?:[.,]\d+)?"
NUMERIC_CLAIM_PATTERN = re.compile(
    rf"(?<![\w.])(?P<number>{_GROUPED_NUMBER}"
    rf"(?:\s*(?:-|\u2013|\u2014)\s*{_GROUPED_NUMBER})?)(?!\d|\.\d)",
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


# A space between digits followed by exactly three more, and no fourth: a
# thousands group, so "7 800" becomes "7800" on both the source and the claim.
#
# The sponsoring directory writes amounts in space-grouped and continental
# notation -- Algeria states "7 800DZD" and "0,200CC" -- and a model asked in
# English writes "7,800" and "0.200". Neither was found in the source, so the
# sentence stating the minimum order was deleted, and with nothing left the
# answer fell back to "the approved policy documents do not contain enough
# information". Observed live on 2026-09-08; four of six natural renderings of
# that record produced an empty answer.
#
# Only a SPACE is stripped, never a comma or a point. A space is never a
# decimal separator, so "7 800" can only be 7800. A comma or point before
# three digits is genuinely ambiguous -- "1,000" and "1.000" are one thousand
# and one, depending on locale -- and this corpus states Case Credit
# thresholds, where guessing wrong is a 1000x error in a number a distributor
# acts on. test_numeric_grounding_does_not_treat_thousands_separator_as_decimal
# holds that line and is right to.
_DIGIT_GROUP_RE = re.compile(r"(?<=\d)[ \u00a0\u202f](?=\d{3}(?!\d))")


def _normalize(text: str) -> str:
    """Normalize text for tolerant, Unicode-safe source matching."""
    normalized = unicodedata.normalize("NFKC", text or "").casefold()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"\s*(?:-|\u2013|\u2014)\s*", "-", normalized)
    normalized = _DIGIT_GROUP_RE.sub("", normalized)
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

    # A leading zero settles the ambiguity a three-digit tail otherwise carries.
    # "0,200" cannot be a thousands group -- that would just be "200" -- so it
    # is a decimal and "0.200" is the same figure. Algeria's minimum order is
    # written "0,200CC" and a model asked in English renders it "0.200".
    # "1,000" against "1.000" stays ambiguous and is deliberately not covered.
    leading_zero = re.fullmatch(r"0(?P<separator>[.,])(?P<fraction>\d{3,})", normalized)
    if leading_zero:
        other_separator = "," if leading_zero.group("separator") == "." else "."
        variants.add(f"0{other_separator}{leading_zero.group('fraction')}")

    # A grouped thousand also appears ungrouped: a source writing "7 800"
    # normalises to "7800", and an answer writing "7,800" has to be able to
    # reach it. Offered as an alternative to try, never as a replacement, so
    # "1.000" still fails to find "1,000" and the 1000x confusion stays caught.
    grouped = re.fullmatch(r"(?P<whole>\d{1,3})(?P<separator>[.,])(?P<group>\d{3})", normalized)
    if grouped and grouped.group("whole") != "0":
        variants.add(f"{grouped.group('whole')}{grouped.group('group')}")
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
    """Extract title-like phrases without a language-specific alphabet or stopword list.

    A phrase never spans a line break or sentence boundary. Word extraction
    discards punctuation, so a heading used to merge into the sentence beneath it:
    "How to Become a Recognized Manager\\n\\nYou must generate..." yielded the
    entity "Recognized Manager You", whose tokens matched no subject in the
    source. The number was then reported ungrounded and the whole answer was
    replaced by the insufficient-evidence fallback.
    """
    entities: list[str] = []
    for segment in re.split(r"[\n\r]+|(?<=[.!?:;])\s", text):
        current: list[str] = []
        for word in re.findall(r"[^\W\d_]+", segment, flags=re.UNICODE):
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
    # repeated values to the first subject instead of the current claim. The
    # prefix is already bounded to what precedes THIS occurrence.
    #
    # Bound the subject to the claim's own sentence. A heading two lines above
    # was supplying it: "Requirements to Reach Supervisor" gave {reach,
    # supervisor}, and every token must appear in the source window, so a source
    # sentence reading "Supervisor is achieved by generating a total of 10 Open
    # Group Case Credits" did not match. 10 was reported ungrounded, and the
    # sentence stating the requirement was deleted from the answer or the whole
    # answer was replaced. Measured live on rank-qualification questions, which
    # are close to this bot's core purpose.
    #
    # With no named subject in the sentence, the existing lexical-overlap path
    # applies, which is the same treatment as scripts that do not capitalise.
    # Only a line break or a sentence end bounds the subject. A colon must not:
    # "To qualify as Assistant Manager ... two paths: generate 120 ..." keeps its
    # subject after the colon, and cutting there let a number belonging to
    # another rank pass as grounded.
    sentence_prefix = re.split(r"[\n\r]|(?<=[.!?])\s", claim.prefix)[-1]
    phrases = _capitalized_entity_phrases(sentence_prefix)
    phrases = [phrase for phrase in phrases if len(_word_tokens(phrase)) >= 2][-1:]

    token_sets: list[set[str]] = []
    for phrase in phrases:
        words = re.findall(r"[^\W\d_]+", phrase, flags=re.UNICODE)
        # Consider every contiguous multi-word span, not only suffixes. A leading
        # grammatical word ("For Assistant Manager") was already handled; a
        # TRAILING one was not, so a heading like "Recognized Manager
        # Requirements" produced only spans containing "requirements", which
        # appears in no source, and a correct grounded number was rejected.
        # The number itself must still be present in the source: these spans only
        # decide which occurrence a number is bound to.
        for start in range(len(words)):
            for end in range(len(words), start + 1, -1):
                tokens = _word_tokens(" ".join(words[start:end]))
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


# A clock time, written with either separator: 09:00, 09.00, 9:00.
#
# The trailing guard rejects a further digit ("1:234") and a further
# separator-plus-digit ("09.00.30", hours.minutes.seconds), but must allow a
# sentence period: "The office opens at 09:00." is the ordinary case, and
# excluding it made this pattern match nothing at all.
#
# A decimal such as "1.50" also matches this shape. That is harmless here: the
# only effect of matching is to spare a figure from deletion when a source
# states the same figure, which is exactly what should happen anyway.
_TIME_RE = re.compile(r"(?<![\d:.])(\d{1,2})[:.](\d{2})(?!\d)(?![:.]\d)")
# "5:00 pm" following the time, allowing "p.m." and a non-breaking space.
_MERIDIEM_RE = re.compile(r"^[\s ]*([ap])\.?\s?m\.?\b", re.I)


# An hour with a meridiem and no minutes: "9am", "6 pm", "8 p.m.".
#
# Three of the 113 directory records that state office hours are written this
# way -- England, Ireland and Scotland, all as "Monday - 9am - 6pm" -- and the
# pattern above finds no time in them at all. Without this, a model writing
# 09:00-18:00 for those markets has nothing in the source to match against and
# loses the hours, which is the failure this whole check exists to prevent.
_HOUR_MERIDIEM_RE = re.compile(r"(?<![\d:.])(\d{1,2})\s?([ap])\.?\s?m\.?\b", re.I)


def _meridiem_hour_keys(match: re.Match[str]) -> set[str]:
    """Return the 24-hour form of an hour written without minutes."""
    hour = int(match.group(1))
    if match.group(2).lower() == "p" and hour < 12:
        hour += 12
    elif match.group(2).lower() == "a" and hour == 12:
        hour = 0
    return {f"{hour:02d}00"}


def _time_occurrences(text: str) -> list[tuple[int, int, set[str]]]:
    """Every clock time in the text, in whichever notation it is written."""
    occurrences = [
        (match.start(), match.end(), _time_keys(text, match))
        for match in _TIME_RE.finditer(text)
    ]
    occurrences += [
        (match.start(), match.end(), _meridiem_hour_keys(match))
        for match in _HOUR_MERIDIEM_RE.finditer(text)
    ]
    return sorted(occurrences)


def _time_keys(text: str, match: re.Match[str]) -> set[str]:
    """Return the 24-hour forms one written time could mean.

    Zero-padded so "9:00" and "09.00" compare equal, which is the whole point:
    the directory writes office hours as 09.00-17.00 and the model writes them
    as 09:00-17:00, so a literal comparison never matched and every component
    was reported ungrounded.

    A pm time is also offered in 24-hour form, because a model given
    "17.00" frequently writes "5:00 pm".
    """
    hour, minute = int(match.group(1)), match.group(2)
    keys = {f"{hour:02d}{minute}"}
    meridiem = _MERIDIEM_RE.match(text[match.end():])
    if meridiem and meridiem.group(1).lower() == "p" and hour < 12:
        keys.add(f"{hour + 12:02d}{minute}")
    if meridiem and meridiem.group(1).lower() == "a" and hour == 12:
        keys.add(f"00{minute}")
    return keys


def _grounded_time_spans(answer: str, source_texts: list[str]) -> list[tuple[int, int]]:
    """Spans holding a clock time that a source states, in either notation.

    Office hours were being deleted from directory contact answers because of a
    notation mismatch alone. Observed live on 2026-09-08: 09.00-17.00 in the
    Belgium record, 09:00-17:00 in the answer, and the whole sentence removed.
    """
    approved: set[str] = set()
    for source in source_texts:
        for _, _, keys in _time_occurrences(source):
            approved |= keys

    spans = [(start, end) for start, end, keys in _time_occurrences(answer) if keys & approved]

    # Two grounded times joined into a range must become one span. The claim
    # extractor reads "09:00-17:00" greedily and produces "00-17", a claim that
    # begins inside the first time and ends inside the second, so it sits in
    # neither span on its own and would still be reported ungrounded.
    #
    # Times are merged only across a short gap containing no digits, which
    # covers "-", " to ", " bis ", " a " and the meridiem in "9:00 am to
    # 5:00 pm", without reaching across a sentence or joining a grounded time
    # to an invented one further along.
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged:
            gap = answer[merged[-1][1]:start]
            if len(gap) <= 8 and not any(character.isdigit() for character in gap):
                merged[-1] = (merged[-1][0], end)
                continue
        merged.append((start, end))
    return merged


def unsupported_numeric_claims(answer: str, source_documents: list[object]) -> list[MeasurableClaim]:
    """Return factual numeric claims that no retrieved source supports."""
    source_texts = [
        _normalize(str(getattr(document, "content", "") or ""))
        for document in source_documents
        if getattr(document, "content", "")
    ]
    if not source_texts:
        return []
    grounded_spans = _grounded_phone_spans(answer, source_texts) + _grounded_time_spans(answer, source_texts)
    return [
        claim
        for claim in _extract_claims(answer)
        if not any(start <= claim.start and claim.end <= end for start, end in grounded_spans)
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
    repaired = _drop_orphaned_delimiters(repaired)
    repaired = re.sub(r"[ \t]+\n", "\n", repaired)
    repaired = re.sub(r"\n{3,}", "\n\n", repaired).strip()
    repaired = _drop_orphaned_lead_ins(repaired)
    return repaired, [claim.text for claim in unsupported]


def _drop_orphaned_lead_ins(text: str) -> str:
    """Remove a line that introduces content this repair deleted.

    A colon is not a sentence boundary, so a lead-in survives while everything
    it promised is removed. Observed live on 2026-09-08 for "what is the
    delivery cost for sweden?", which was delivered as:

        For Sweden, the delivery costs are:

        The average lead time for orders to arrive in Sweden is 4-7 days.

    The costs were ungrounded and correctly removed; the promise of them was
    not, and the reader was left with a heading over nothing and an unrelated
    fact beneath it. That reads as a rendering fault and quietly loses the
    question that was asked.

    Only a lead-in whose own content is gone is dropped: one still followed by
    an indented or bulleted line is doing its job and is left alone. This is
    the same repair as _drop_orphaned_delimiters above, one level up - a
    fragment whose partner this function removed.
    """
    lines = text.split("\n")
    kept: list[str] = []
    for index, line in enumerate(lines):
        if line.rstrip().endswith(":"):
            following = next(
                (candidate for candidate in lines[index + 1:] if candidate.strip()),
                "",
            )
            # A list or an indented block is what a lead-in introduces. Ordinary
            # prose beneath it is a new statement, not the promised content.
            introduces_content = bool(
                re.match(r"\s*(?:[-*•]|\d+[.)]|[a-z][.)])\s", following)
                or (following[:1].isspace() if following else False)
            )
            if not introduces_content:
                continue
        kept.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def _drop_orphaned_delimiters(text: str) -> str:
    """Remove brackets this repair orphaned, never a matched pair.

    Removing a sentence can cut one half of a parenthetical aside. Measured at
    1 in 10 on "How can i become a recognized manager?": the model wrote
    "(There is an exception: ... 999 Case Credits ...)", repair deleted the
    sentence holding the number, the stray ")" survived, and the integrity
    validator then read the unbalanced text as truncated and replaced the entire
    answer with "the approved policy documents do not contain enough
    information" - for a question the documents answer in full.

    Only delimiters with no partner are dropped, so text the repair did not
    touch is unchanged.
    """
    removable: set[int] = set()
    for opener, closer in (("(", ")"), ("[", "]")):
        open_positions: list[int] = []
        for index, character in enumerate(text):
            if character == opener:
                open_positions.append(index)
            elif character == closer:
                if open_positions:
                    open_positions.pop()
                else:
                    removable.add(index)
        removable.update(open_positions)
    if not removable:
        return text
    cleaned = "".join(char for index, char in enumerate(text) if index not in removable)
    return re.sub(r"\s+([,.;:!?])", r"\1", re.sub(r"[ \t]{2,}", " ", cleaned))


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
