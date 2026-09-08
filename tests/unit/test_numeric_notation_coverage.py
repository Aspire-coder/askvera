"""Notation coverage derived from real corpus text, not from imagination.

Every notation bug found so far was a mismatch between how the corpus writes a
number and how a model writes the same number, and each was found one at a time
by someone running into it:

    record "7 800DZD"   model "7,800"    sentence deleted
    record "0,200CC"    model "0.200"    sentence deleted
    record "$7.5"       model "$7.50"    whole answer discarded
    record "48h to 96h" model "48-96"    figure removed

Nobody predicted any of them, and authoring a test per notation only ever
catches the one already known. This generates the renderings instead: it takes
real record text, finds the figures in it, re-renders each the ways a model
plausibly would, and asserts the grounding check still recognises its own
source.

The claim sentence is the source clause with only the number re-rendered, so a
failure means the notation was rejected rather than the subject matching being
imperfect. That isolation is the point - subject matching has its own tests.
"""

from __future__ import annotations

import re

import pytest

from app.retrieval.models import RetrievedDocument
from app.validation.validators.numeric_grounding_validator import (
    _phone_matches,
    unsupported_numeric_claims,
)

# Verbatim excerpts dumped from askvera-policy-sections on 2026-09-08 with
# scripts/dump_corpus_sections.py. Kept short, and kept exactly as the corpus
# writes them - reformatting them here would defeat the entire purpose.
ALGERIA = (
    "Welcome to Forever Algeria! Minimum order size FBO: 0,200CC as a first order for Preferred "
    "Customers, 7 800DZD ($60) and the equivalent of 5 000 DZD ($43) after the first purchase for "
    "all FBOs. Delivery Cost: 900 DZD ($7.5). Average lead time for orders to arrive: between 48h "
    "to 96h, exception made for the extreme southern part of the country."
)
REUNION = (
    "Forever Reunion Island. Delivery cost are at 6EUR and free for orders exceeding 1CC. "
    "The GO2FBO pack costs 352.38EUR and it represents 1.612CC."
)
FRANCE = (
    "Forever France. A newly sponsored Preferred Customer will have to order 150EUR minimum of "
    "products within 72 hours. The Discovery Pack is worth 0,540CC at 150EUR. Forever France "
    "transfers bonuses to local accounts if the bonus amount exceeds 5EUR."
)

# Title and section travel with the content: the grounding check reads the
# document's market from its title, so pairing Reunion text with Algeria's
# title tests nothing but the mismatch.
RECORDS = {
    "algeria": (ALGERIA, "Forever Algeria", "sponsoring-001-algeria"),
    "reunion": (REUNION, "Forever Reunion Island", "sponsoring-084-r-union-island"),
    "france": (FRANCE, "Forever France", "sponsoring-063-france"),
}

# A figure carrying a unit or currency: the class of value a reader acts on.
# Phone numbers and clock times are excluded because they have their own
# grounded-span handling and their own tests.
_FIGURE_RE = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:[ ,.]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
    r"(?=\s?(?:CC|DZD|EUR|USD|%|h\b|hours\b)|\s?(?:to|-)\s?\d)"
    r"|\$(\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
_TIME_RE = re.compile(r"\d{1,2}[.:]\d{2}")


def _renderings(number: str) -> set[str]:
    """Ways a model plausibly writes the same value.

    Deliberately conservative. A space between digit groups is unambiguously a
    thousands separator, so "7 800" may also be written "7800" or "7,800". A
    point or comma is not: "1.612CC" is one and a half Case Credits, and
    offering "1612" as an alternative rendering would assert the very 1000x
    confusion the validator is right to refuse.
    """
    variants = {number}

    if " " in number:
        compact = number.replace(" ", "")
        variants.update({compact, f"{compact[:-3]},{compact[-3:]}"})
        return variants

    decimal = re.fullmatch(r"(\d+)([.,])(\d+)", number)
    if decimal:
        whole, separator, fraction = decimal.groups()
        other = "," if separator == "." else "."
        trimmed = fraction.rstrip("0") or "0"

        # Swapping the separator is only offered where the value stays
        # unambiguous. "1.612CC" written "1,612CC" could equally be read as one
        # thousand six hundred and twelve, and the validator refuses that pair
        # on purpose - a 1000x error in a Case Credit threshold is one a
        # distributor acts on. A leading zero settles it, because "0,200" can
        # only be a decimal.
        if len(fraction) != 3 or whole == "0":
            variants.add(f"{whole}{other}{fraction}")
            variants.add(f"{whole}{other}{trimmed}")

        # Zeros are added or dropped in the record's own notation. A model
        # writes "7.50" where the record says "7.5", or "0.2" where it says
        # "0,200"; it does not swap the separator and pad in one step.
        variants.add(f"{whole}{separator}{trimmed}")
        if len(fraction) <= 2:
            variants.add(f"{whole}{separator}{fraction}0")
    return {value for value in variants if value}


def _figures(text: str) -> list[str]:
    """Figures worth checking, excluding phone numbers and clock times."""
    phone_spans = [(m.start(), m.end()) for m in _phone_matches(text)]
    found: list[str] = []
    for match in _FIGURE_RE.finditer(text):
        if any(start <= match.start() < end for start, end in phone_spans):
            continue
        if _TIME_RE.fullmatch(match.group(0)):
            continue
        value = (match.group(1) or match.group(2) or "").strip()
        if value and value not in found:
            found.append(value)
    return found


def _document(content: str, title: str, section_id: str) -> RetrievedDocument:
    return RetrievedDocument(
        id=section_id,
        title=f"International-Sponsoring-Directory.pdf - {title}",
        content=content,
        source="s3://askverachat-prod-kb/approved/Global_en/directories/"
        "International-Sponsoring-Directory.pdf",
        page="5",
        metadata={
            "access_scope": "global",
            "directory_section": "sponsoring",
            "section_id": section_id,
        },
    )


def _clause_for(text: str, number: str) -> str:
    """The sentence in the record that states this figure."""
    for sentence in re.split(r"(?<=[.!?])\s", text):
        if number in sentence:
            return sentence
    raise AssertionError(f"{number!r} not found in a sentence of the record")


def _cases() -> list[tuple[str, str, str]]:
    collected: list[tuple[str, str, str]] = []
    for name, (text, _title, _section) in RECORDS.items():
        for number in _figures(text):
            for rendering in sorted(_renderings(number)):
                collected.append((name, number, rendering))
    return collected


CASES = _cases()


def test_the_generator_found_figures_in_every_record() -> None:
    """A silent zero-case run would make every assertion below vacuous."""
    for name, (text, _title, _section) in RECORDS.items():
        assert _figures(text), name
    assert len(CASES) > 25, len(CASES)


@pytest.mark.parametrize("record,number,rendering", CASES, ids=lambda value: str(value))
def test_a_re_rendered_figure_stays_grounded(record: str, number: str, rendering: str) -> None:
    """The same value written differently must still match its own source."""
    text, title, section_id = RECORDS[record]
    answer = _clause_for(text, number).replace(number, rendering)
    document = _document(text, title, section_id)

    unsupported = [claim.number for claim in unsupported_numeric_claims(answer, [document])]

    assert not unsupported, (
        f"{record}: the record writes {number!r} and an answer writing {rendering!r} "
        f"was rejected as ungrounded ({unsupported})"
    )
