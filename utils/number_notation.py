"""Reading a figure the way the document that wrote it meant it.

The corpus does not agree with itself about notation, because the records were
written in different places:

    "0,200CC"        comma as the decimal separator
    "7 800DZD"       space as the group separator
    "5 000 DZD"      the same, spaced from its unit
    "1,612CC"        the France record - and the reason this exists
    "$7.5"           dot as the decimal separator

An English answer that repeats "1,612CC" is read as one thousand six hundred
and twelve. The French record means 1.612. Nothing in the pipeline knew the
difference, so the string was copied across and the reader was misinformed by a
figure that was, character for character, correct.

This module decides what a written figure means, and says why. Three things
follow from the shape of the problem and are not negotiable here:

**Nothing is guessed.** "1,612" on its own is genuinely ambiguous - it is 1612
in English and 1.612 in French - and a reading that picks one is wrong half the
time in a way nobody can see. Ambiguity returns `resolved=False` and no value.
The caller then has the choice it should have: leave the original text alone,
or refuse. It never has a confident wrong number.

**The evidence is the document, never the country.** A France-specific rule
would be a rule about which record we happened to look at, and would be wrong
for the next French-language record written elsewhere, and for the English
record that happens to use a comma. What resolves "1,612CC" in the Algeria
record is "0,200CC" in the same record: a comma with a leading zero in front of
it cannot be a thousands group, so that document uses the comma as its decimal
separator, so the ambiguous figure does too.

**Every reading carries its own justification.** `NumberReading` holds the text
as written, the value, the unit and the evidence in words, together. A value
without its evidence is an assertion, and this is exactly the kind of assertion
that needs to be auditable when a distributor disputes a figure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

# Space-like characters used as group separators in the corpus. The narrow
# no-break space is what most French typesetting produces and is invisible in a
# terminal, which is how it survives unnoticed into a comparison.
_SPACES = "    "

# A figure with optional group and decimal separators, e.g. 7 800, 1,612.50,
# 0,200, 1.612, 60.
_NUMBER_RE = re.compile(
    rf"(?<![\d.,])\d{{1,3}}(?:[{_SPACES}.,]\d{{3}})*(?:[.,]\d+)?(?![\d])"
    rf"|(?<![\d.,])\d+(?:[.,]\d+)?(?![\d])"
)

# The unit written against a figure. Currency codes and the business units the
# records use; a symbol before the figure is handled separately.
_UNIT_AFTER_RE = re.compile(r"[ \t]?([A-Za-z]{2,3}|%)(?![A-Za-z])")
_SYMBOL_BEFORE_RE = re.compile(r"([$€£])[ \t]?$")


@dataclass(frozen=True)
class NumberReading:
    """One figure, as written and as understood, with the reason for both."""

    text: str
    """Exactly the characters the source used. Never normalised away."""

    value: Decimal | None
    """What the figure means. None when it could not be decided."""

    unit: str
    """The currency or business unit written against it, or "" if none was."""

    evidence: str
    """Why this reading, in words. Present for an unresolved reading too."""

    resolved: bool
    """False means genuinely ambiguous. It does not mean zero, or absent."""


def _normalize_spaces(value: str) -> str:
    return "".join(" " if char in _SPACES else char for char in value or "")


def _decimal(digits: str) -> Decimal | None:
    try:
        return Decimal(digits)
    except InvalidOperation:
        return None


def _separators(text: str) -> tuple[list[str], str]:
    """The separators in a figure, in order, and its trailing group if any."""
    found = [char for char in text if char in ".," or char in _SPACES]
    return [" " if char in _SPACES else char for char in found], text


def document_decimal_separator(document_text: str) -> tuple[str | None, str]:
    """Which separator this document uses for decimals, and how we know.

    Decided only from figures that cannot be read two ways:

    - a separator followed by anything other than exactly three digits
      ("7,5", "$7.50") is a decimal separator, since a thousands group is
      always three digits;
    - a separator preceded by a lone zero ("0,200") is a decimal separator,
      since no thousands group follows a leading zero.

    A document that never writes such a figure returns None, and its ambiguous
    figures stay ambiguous. Returning a guess here would spread one guess over
    every figure in the record.
    """
    text = _normalize_spaces(document_text or "")
    for separator in (",", "."):
        escaped = re.escape(separator)
        short_group = re.search(rf"\d{escaped}(\d{{1,2}}|\d{{4,}})(?!\d)", text)
        if short_group:
            return separator, (
                f"the document writes {short_group.group(0)!r}, and a thousands "
                f"group is always three digits, so {separator!r} separates decimals here"
            )
        leading_zero = re.search(rf"(?<!\d)0{escaped}\d+", text)
        if leading_zero:
            return separator, (
                f"the document writes {leading_zero.group(0)!r}, and no thousands "
                f"group follows a leading zero, so {separator!r} separates decimals here"
            )
    return None, "the document contains no figure that fixes its decimal separator"


def _unit_for(text: str, start: int, end: int) -> str:
    """The unit written against a figure, if the source wrote one."""
    after = _UNIT_AFTER_RE.match(text, end)
    if after:
        return after.group(1)
    before = _SYMBOL_BEFORE_RE.search(text[:start])
    if before:
        return before.group(1)
    return ""


def read_number(text: str, *, document_text: str = "") -> NumberReading:
    """Read a single written figure. See `readings_in` for a whole sentence."""
    readings = readings_in(text, document_text=document_text)
    if readings:
        return readings[0]
    return NumberReading(
        text=text, value=None, unit="", evidence="no figure found", resolved=False
    )


def readings_in(text: str, *, document_text: str = "") -> list[NumberReading]:
    """Every figure in `text`, read against the conventions of its document.

    `document_text` is the record the figure was taken from. Passing the same
    string twice is fine - a sentence is evidence about itself - but a longer
    record resolves more, which is the point: "1,612CC" alone is ambiguous and
    "1,612CC" in a record that also says "0,200CC" is not.
    """
    source = _normalize_spaces(text)
    evidence_separator, separator_evidence = document_decimal_separator(
        _normalize_spaces(document_text) or source
    )

    readings: list[NumberReading] = []
    for match in _NUMBER_RE.finditer(source):
        written = match.group(0)
        unit = _unit_for(source, match.start(), match.end())
        value, evidence, resolved = _interpret(
            written, evidence_separator, separator_evidence
        )
        readings.append(
            NumberReading(
                text=text[match.start() : match.end()],
                value=value,
                unit=unit,
                evidence=evidence,
                resolved=resolved,
            )
        )
    return readings


def _interpret(
    written: str,
    evidence_separator: str | None,
    separator_evidence: str,
) -> tuple[Decimal | None, str, bool]:
    """Decide what one figure means, in the order the evidence is strongest."""
    separators, _ = _separators(written)
    digits_only = re.sub(r"[^\d]", "", written)

    if not separators:
        value = _decimal(digits_only)
        return value, "the figure has no separator", value is not None

    distinct = {separator for separator in separators}
    last = separators[-1]
    tail = written.rsplit(
        next(char for char in reversed(written) if char in ".," or char in _SPACES), 1
    )[-1]

    # Two different separators: the later one separates the decimal part.
    # "1,612.50" and "1 612,50" are both unambiguous for this reason.
    if len(distinct) > 1:
        if last == " ":
            return (
                _decimal(digits_only),
                "a space never separates decimals, so every separator groups digits",
                True,
            )
        whole = re.sub(r"[^\d]", "", written[: len(written) - len(tail) - 1])
        value = _decimal(f"{whole}.{tail}")
        return (
            value,
            f"the figure uses both separators, so the last one ({last!r}) "
            "separates the decimal part",
            value is not None,
        )

    # A space only ever groups digits.
    if last == " ":
        return (
            _decimal(digits_only),
            "a space never separates decimals, so it groups digits",
            True,
        )

    # One separator kind. Three trailing digits is the ambiguous shape, and
    # only then.
    if len(separators) > 1:
        return (
            _decimal(digits_only),
            f"{last!r} appears more than once, so it groups digits",
            True,
        )

    whole = written[: len(written) - len(tail) - 1]
    if len(tail) != 3:
        value = _decimal(f"{re.sub(r'[^0-9]', '', whole)}.{tail}")
        return (
            value,
            f"{len(tail)} digits follow {last!r} and a thousands group is always "
            "three, so it separates decimals",
            value is not None,
        )
    if whole.lstrip("0") != whole or whole == "0":
        value = _decimal(f"{whole}.{tail}")
        return (
            value,
            f"a leading zero precedes {last!r}, and no thousands group follows "
            "a leading zero, so it separates decimals",
            value is not None,
        )

    if evidence_separator == last:
        value = _decimal(f"{whole}.{tail}")
        return value, separator_evidence, value is not None
    if evidence_separator is not None:
        return (
            _decimal(digits_only),
            f"{separator_evidence}; {last!r} therefore groups digits",
            True,
        )

    return (
        None,
        f"{written!r} could be a decimal or a thousands group, and the document "
        "contains no figure that decides which - left unresolved rather than guessed",
        False,
    )
