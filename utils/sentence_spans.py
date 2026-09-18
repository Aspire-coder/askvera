"""Span-aware sentence boundary detection shared by post-generation editors.

Every editor that deletes or compares text after generation has needed to
answer the same question: is this "." (or "!"/"?") the end of a sentence, or
just a character that happens to look like one? A naive ``[.!?](?=\\s|$)``
regex gets this wrong for the shapes that appear constantly in policy
answers - decimal numbers, clock times, currency, abbreviations, initials,
emails, URLs and clause references - and a wrong answer here does not just
mis-count sentences, it corrupts the visible answer: whatever text sits
between two wrongly-detected boundaries gets deleted or kept as its own unit.

The concrete failure this module exists to prevent (observed live, before the
fix in ``utils/directory_fields.py``'s order-size branch): removing the
sentence "Business hours are 09.00 am - 19.00 pm." left the fragment
"00 am - 19.00 pm." behind, because a bare period search ended the sentence at
the "." inside "09.00". The same shape of bug reproduces in
``app/validation/validators/numeric_grounding_validator.py``'s
``remove_unsupported_numeric_sentences``: deleting an unsupported numeric
claim after an abbreviation like "approx." or "Nr." or after an initial like
"J." leaves "The fee is approx." or "Contact J. R." standing as the answer.

Rule implemented here: a "." ends a sentence only when it is followed by
whitespace plus an uppercase letter or an opening quote, or by the end of
text - and never when it sits inside a number, an email address, a URL, or
directly after a known abbreviation or a single-letter initial. "!" and "?"
follow the same followed-by-uppercase-or-quote-or-end test, so a run of
closing punctuation such as "?!" or "..." collapses to one boundary at its
last character, and a mid-run character (the first "." of "...", or "?" in
"?!") is never mistaken for a boundary on its own.

This module is deliberately small: one abbreviation list, documented by
language, and no per-editor special cases. Editors that need those (order-size
duration wording, business-hours phrasing, directory field labels) keep that
logic themselves and call here only for "where does this sentence end".
"""

from __future__ import annotations

import re
import unicodedata
from typing import NamedTuple

__all__ = [
    "ABBREVIATIONS",
    "SentenceSpan",
    "abbreviation_or_initial_before",
    "iter_sentences",
    "sentence_boundaries",
    "split_sentences",
    "is_sentence_boundary",
]


class SentenceSpan(NamedTuple):
    """One sentence-like segment of the original text, with its character span.

    ``text`` is exactly ``source[start:end]`` - callers that need trimmed text
    call ``.strip()`` themselves, so this module never decides what counts as
    "the same" span across different callers' whitespace conventions.
    """

    text: str
    start: int
    end: int


# Abbreviations that end in "." without ending a sentence, grouped by the
# language they are documented for. Lower-cased, without the trailing dot -
# the matcher folds case and supplies the dot itself. Kept short on purpose:
# this list is a known-exception list, not a dictionary, and every entry
# should be one this module has actually needed for a reproduced defect or a
# clearly analogous one, not a speculative addition.
ABBREVIATIONS: frozenset[str] = frozenset(
    {
        # English
        "e.g", "i.e", "etc", "approx", "vs", "no", "nr", "ca",
        "mr", "mrs", "ms", "dr", "prof", "st", "jr", "sr", "vol", "fig", "ref", "pp",
        "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
        # German
        "z.b", "bzw", "usw", "ggf", "inkl", "exkl", "std", "u.a", "d.h",
        # French
        "p.ex", "cf", "svp", "etc.al",
        # Spanish / Portuguese
        "sr", "sra", "dr", "dra", "ud", "uds",
        # Italian
        "sig", "dott", "sigg",
        # Dutch
        "dhr", "mevr", "bv", "ev",
        # Scandinavian
        "t.ex", "f.eks", "osv", "bl.a",
    }
)

# A run of one or more terminal-punctuation characters, treated as a single
# candidate boundary anchored on its LAST character - so "?!" and "..." each
# collapse to one decision instead of three independent, mostly-wrong ones.
_TERMINAL_RUN_RE = re.compile(r"[.!?]+|…")

# A number: digits with an optional single "." or "," fractional/grouping
# separator on either side of the candidate dot, so "09.00", "3.5", "1,234.56"
# and "1.234,56" never split on the internal dot. Applied by checking whether
# the character immediately before and the character immediately after the
# run are both digits.
_DIGIT_RE = re.compile(r"\d")

# Email and URL spans: any "." (or "!"/"?" inside a URL's path or query) that
# falls inside one of these is never a boundary, regardless of what
# surrounds it in the outer sentence.
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)

# A bare list/outline marker at the start of a line: "1.", "16.02(k)." is
# already excluded by the digit-digit rule for the inner dot, but a lone
# leading "1." before a capitalised word ("1. Introduction") reads as a
# boundary under the uppercase-follows rule though it introduces a list item,
# not a new sentence. Anchored to the start of a line (or text) so it never
# matches a number that merely follows whitespace mid-sentence.
_LIST_MARKER_RE = re.compile(r"(?:^|\n)[ \t]*\(?\d{1,3}\)?$")

# An initial: a single uppercase letter standing alone as its own "word"
# immediately before the candidate dot ("J. R. Smith"). Distinguished from a
# sentence-initial word by requiring the character before that letter to be
# whitespace, the start of text, or another initial's dot.
_INITIAL_RE = re.compile(r"(?:^|[\s(])[A-Za-z]$")

_OPENING_QUOTE_CHARS = "\"'‘“«‹"


def _spans_containing(pattern: re.Pattern[str], text: str) -> list[tuple[int, int]]:
    return [match.span() for match in pattern.finditer(text)]


def _inside_any(position: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in spans)


def _abbreviation_before(text: str, index: int) -> bool:
    """True when the word ending immediately before ``index`` is a known abbreviation."""
    word_match = re.search(r"[^\W\d_]+$", text[:index])
    if not word_match:
        return False
    return word_match.group(0).casefold() in ABBREVIATIONS


def _initial_before(text: str, index: int) -> bool:
    return bool(_INITIAL_RE.search(text[:index]))


def abbreviation_or_initial_before(text: str, index: int) -> bool:
    """True when the "." at ``index`` sits right after a known abbreviation or a single initial.

    Exposed for editors that need this one check without adopting this
    module's fuller ``sentence_boundaries`` boundary rule (which also
    requires an uppercase letter, opening quote, line break or end of text to
    follow before it will call anything a boundary at all). That extra
    "what follows" test is wrong for a caller whose own boundary regex
    already decides that independently: ``app/validation/validators/
    numeric_grounding_validator.py``'s ``remove_unsupported_numeric_sentences``
    read "You must generate 120 Open Group Case Credits. (There is an
    exception ..." as one sentence under the full ``sentence_boundaries``
    rule, because "(" is not uppercase, a quote, or a line break - and then
    deleted the grounded "120" sentence along with the exception clause that
    followed it. This function answers only "is this period read as
    abbreviation punctuation, not a sentence end", leaving what follows to
    the caller's own boundary logic.
    """
    return _abbreviation_before(text, index) or _initial_before(text, index)


def _is_list_marker(text: str, index: int) -> bool:
    return bool(_LIST_MARKER_RE.search(text[:index]))


def _numeric_span(text: str, index: int) -> bool:
    """True when the character before and the first character after this run are both digits."""
    before = text[index - 1] if index > 0 else ""
    after = text[index] if index < len(text) else ""
    return bool(_DIGIT_RE.fullmatch(before) and _DIGIT_RE.fullmatch(after))


def _followed_by_sentence_start(text: str, index: int) -> bool:
    """True when a new sentence - not more of the same one - begins at/after ``index``."""
    rest = text[index:]
    stripped = rest.lstrip(" \t")
    if not stripped:
        return True  # end of text
    if stripped[0] == "\n":
        return True  # a line break always starts a fresh unit
    first_char = stripped[0]
    if first_char in _OPENING_QUOTE_CHARS:
        return True
    category = unicodedata.category(first_char)
    if category == "Lu":  # uppercase letter
        return True
    # A digit, a lowercase letter or anything else opening the next clause
    # is exactly the continuation shape this module must not split: "The fee
    # is approx. 999 USD." must not become two sentences at "approx.".
    return False


def _candidate_boundaries(text: str) -> list[tuple[int, int]]:
    """Every terminal-punctuation run, as ``(start, end)`` spans, in order."""
    return _spans_containing(_TERMINAL_RUN_RE, text)


def sentence_boundaries(text: str) -> list[int]:
    """Return the offsets right after each real sentence-ending punctuation run.

    Drop-in replacement for the boundary lists earlier editors built with a
    bare ``re.compile(r"[.!?](?=\\s|$)")``: each returned integer is a safe
    place to cut, exactly as ``match.end()`` was used before.
    """
    if not text:
        return []
    email_spans = _spans_containing(_EMAIL_RE, text)
    url_spans = _spans_containing(_URL_RE, text)
    protected_spans = email_spans + url_spans
    boundaries: list[int] = []
    for start, end in _candidate_boundaries(text):
        if _inside_any(start, protected_spans):
            continue
        last_char_index = end - 1
        last_char = text[last_char_index]
        if last_char == "." or text[start:end] == "…":
            if _numeric_span(text, last_char_index if last_char == "." else start):
                continue
            if last_char == "." and (
                _abbreviation_before(text, last_char_index)
                or _initial_before(text, last_char_index)
                or _is_list_marker(text, last_char_index)
            ):
                continue
        if _followed_by_sentence_start(text, end):
            boundaries.append(end)
    return boundaries


def is_sentence_boundary(text: str, end: int) -> bool:
    """True when ``end`` (an offset just past a terminal punctuation run) is a real boundary."""
    return end in sentence_boundaries(text)


def iter_sentences(text: str) -> list[SentenceSpan]:
    """Split ``text`` into sentence-like spans covering it completely, in order.

    Every character of ``text`` belongs to exactly one returned span; nothing
    is dropped, so joining the spans back together reproduces ``text``
    exactly. This is the shape ``app/response/builder.py`` and
    ``app/evidence_contract.py`` need for comparing "the model's sentences"
    against delivered text, and what ``remove_unsupported_numeric_sentences``
    and directory-field editors need for "where does the sentence around this
    claim start and end".
    """
    if not text:
        return []
    boundaries = sentence_boundaries(text)
    spans: list[SentenceSpan] = []
    start = 0
    for boundary in boundaries:
        if boundary <= start:
            continue
        spans.append(SentenceSpan(text[start:boundary], start, boundary))
        start = boundary
    if start < len(text):
        spans.append(SentenceSpan(text[start:], start, len(text)))
    return spans


def split_sentences(text: str, *, strip: bool = True) -> list[str]:
    """Return the sentence texts of ``text``, dropping empty segments.

    Replacement for call sites that used ``re.split(r"(?<=[.!?])\\s+|\\n", text)``
    - the split is span-aware instead of a bare-period cut, so a decimal,
    abbreviation, initial, email or URL never becomes a false boundary.
    """
    sentences = []
    for span in iter_sentences(text):
        candidate = span.text.strip() if strip else span.text
        if candidate:
            sentences.append(candidate)
    return sentences
