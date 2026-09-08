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


# A range is written in the source with units and a joining word, and in an
# answer as a dash. Kept as explicit pairs rather than generated, because the
# source form is prose rather than a re-rendering of a single figure.
RANGE_CASES = [
    ("between 48h to 96h", "48-96"),
    ("between 48h to 96h", "48\u201396"),
    ("between 48h to 96h", "48 - 96"),
    ("delivery in 24 to 72 hours", "24-72"),
    ("delivery in 24-72 hours", "24 to 72"),
]


@pytest.mark.parametrize("source_form,answer_form", RANGE_CASES)
def test_a_range_matches_however_the_record_writes_it(source_form: str, answer_form: str) -> None:
    """Observed live: the record says "between 48h to 96h", the model wrote
    "48-96", and repair deleted a correctly stated delivery time.

    Only the endpoints and their order carry meaning; the unit letters and the
    joining word are presentation.
    """
    text = f"Forever Algeria. Average lead time for orders to arrive: {source_form}."
    answer = f"Average lead time for orders to arrive in Algeria is {answer_form} hours."
    document = _document(text, "Forever Algeria", "sponsoring-001-algeria")

    assert not [claim.number for claim in unsupported_numeric_claims(answer, [document])]


def test_a_different_range_is_still_ungrounded() -> None:
    """Flexible joining must not become a flexible value."""
    text = "Forever Algeria. Average lead time for orders to arrive: between 48h to 96h."
    document = _document(text, "Forever Algeria", "sponsoring-001-algeria")

    unsupported = [
        claim.number
        for claim in unsupported_numeric_claims(
            "Average lead time for orders to arrive in Algeria is 24-48 hours.", [document]
        )
    ]
    assert unsupported


def test_an_ordered_list_marker_is_not_a_measurable_claim() -> None:
    """Observed live in the Belgium sponsoring answer: repair removed 3, 4, 5
    and 6 from a delivered answer, taking the sentences with them.

    "3)" and "3:" were already recognised as presentation. "3." - the markdown
    ordered list marker, which is what a model actually writes - was not.
    """
    text = "Forever Belgium. Minimum order size FBO: 1CC."
    answer = (
        "Steps to sponsor:\n\n1. Register online\n2. Confirm the details\n"
        "3. Place a first order\n4. Await approval"
    )
    document = _document(text, "Forever Belgium", "sponsoring-053-belgium")

    assert not [claim.number for claim in unsupported_numeric_claims(answer, [document])]


# Citation support is a third place that asks "does this number appear in the
# source", after grounding and repair. It had its own weaker notion of sameness.
CITATION_CASES = [
    ("The office is open 9:30 AM to 5:30 PM, Saturday to Thursday.", True),
    ("The office is open 09.30 am - 17.30 pm (Sat - Thu).", True),
    ("Delivery costs 900 DZD ($7.50).", True),
    ("Delivery costs 900 DZD ($7.5).", True),
    ("The office is open 8:00 AM to 4:00 PM.", False),
    ("Delivery costs 250 DZD.", False),
]


@pytest.mark.parametrize("answer,should_match", CITATION_CASES)
def test_citation_support_recognises_the_same_value_written_differently(
    answer: str, should_match: bool
) -> None:
    """Measured live: an answer writing "9:30 AM" against a record writing
    "09.30 am" shared no numbers at all, so a correct, retrieved, grounded
    answer was delivered with no citation attached.

    Citation numbers now come from the grounding validator's notation logic
    instead of a private regex, so the two layers agree on what "the same
    figure" means.
    """
    from app.response.builder import ResponseBuilder

    builder = ResponseBuilder.__new__(ResponseBuilder)
    record = (
        "Forever Algeria. Business Hours Office 09.30 am - 17.30 pm (Sat - Thu). "
        "Delivery Cost: 900 DZD ($7.5)."
    )

    shared = builder._numbers(answer) & builder._numbers(record)

    assert bool(shared) is should_match, sorted(shared)


# ---------------------------------------------------------------------------
# Negative controls.
#
# Everything above asserts that a value written differently is still
# recognised. On its own that is a machine for teaching a validator to accept
# anything: every test passes if grounding simply says yes. These generate the
# opposite - the same sentence with the value actually changed - and require
# rejection.
#
# A mutation is only a valid control if the new value is genuinely absent from
# the record. The Algeria record holds 900, 7 800, 60, 5 000, 43, 48 and 96,
# so a mutation that lands on one of those would be correctly grounded and
# would fail this test for the right reason. Those are skipped rather than
# asserted.
# ---------------------------------------------------------------------------


def _mutations(number: str) -> set[str]:
    """Values that differ from the original, in the ways a model gets it wrong."""
    digits = number.replace(" ", "")
    changed: set[str] = set()

    trailing = re.fullmatch(r"(?P<head>.*?)(?P<last>\d)", digits)
    if trailing:
        head, last = trailing.group("head", "last")
        changed.add(f"{head}{(int(last) + 1) % 10}")

    # An order-of-magnitude slip: the failure that matters most in a Case
    # Credit threshold or a currency amount.
    if re.fullmatch(r"\d+", digits):
        changed.add(digits + "0")
    decimal = re.fullmatch(r"(\d+)([.,])(\d+)", digits)
    if decimal:
        whole, separator, fraction = decimal.groups()
        changed.add(f"{whole}{separator}{fraction[:-1]}{(int(fraction[-1]) + 5) % 10}")
        # Moving the separator changes the value by a factor of ten.
        if len(whole) > 1:
            changed.add(f"{whole[:-1]}{separator}{whole[-1]}{fraction}")

    return {value for value in changed if value and value != digits}


def _mutation_cases() -> list[tuple[str, str, str]]:
    collected: list[tuple[str, str, str]] = []
    for name, (text, _title, _section) in RECORDS.items():
        normalized_source = " ".join(text.split())
        for number in _figures(text):
            for mutated in sorted(_mutations(number)):
                # Skip a mutation that happens to be another real figure in the
                # same record: grounding is right to accept it.
                if re.search(rf"(?<![\d.,]){re.escape(mutated)}(?![\d])", normalized_source):
                    continue
                collected.append((name, number, mutated))
    return collected


MUTATION_CASES = _mutation_cases()


def test_the_mutation_generator_produced_controls() -> None:
    """A silent zero-case run would make the rejection assertions vacuous."""
    assert len(MUTATION_CASES) > 15, len(MUTATION_CASES)


@pytest.mark.parametrize("record,number,mutated", MUTATION_CASES, ids=lambda value: str(value))
def test_a_changed_value_is_rejected(record: str, number: str, mutated: str) -> None:
    """The contrast case for every equivalence above.

    Positive-only generated tests risk proving that the validator accepts
    everything. Each of these takes a sentence the record supports and changes
    the figure in it, so grounding has to refuse a claim the source does not
    make.
    """
    text, title, section_id = RECORDS[record]
    answer = _clause_for(text, number).replace(number, mutated)
    document = _document(text, title, section_id)

    unsupported = [claim.number for claim in unsupported_numeric_claims(answer, [document])]

    assert unsupported, (
        f"{record}: the record writes {number!r} and an answer writing {mutated!r} "
        "was accepted as grounded"
    )


# The same figure with a different unit is a different fact. Grounding checked
# the number and the subject and never what the number was denominated in.
UNIT_CASES = [
    ("The delivery cost for orders in Algeria is 900 DZD.", True),
    ("The delivery cost for orders in Algeria is 900 EUR.", False),
    ("The minimum first order is 0,200 DZD.", False),
    ("The minimum first order is 0.200 Case Credits.", True),
    ("The minimum first order is 0.200 CC.", True),
    ("The minimum first order is about $60.", True),
    ("The minimum first order is about 60 EUR.", False),
]


@pytest.mark.parametrize("answer,should_be_grounded", UNIT_CASES)
def test_a_figure_is_bound_to_its_unit(answer: str, should_be_grounded: bool) -> None:
    """900 DZD and 900 EUR are not the same delivery cost.

    Both were accepted before this: the number matched, the subject matched,
    and nothing compared what the figure was denominated in. "0,200CC" being
    reported as "0,200 DZD" is the same defect on a Case Credit threshold,
    which is the kind of number a distributor acts on.
    """
    text, title, section_id = RECORDS["algeria"]
    document = _document(text, title, section_id)

    unsupported = [claim.number for claim in unsupported_numeric_claims(answer, [document])]

    assert (not unsupported) is should_be_grounded, unsupported


def test_an_unlisted_currency_code_does_not_cause_a_false_rejection() -> None:
    """An omission from the currency vocabulary must degrade to no check.

    The source is casefolded before matching, so the unit rule cannot key off
    capitalisation and needs an explicit vocabulary. A code nobody listed
    therefore yields no unit at all, which is exactly the behaviour that
    existed before the check - safe, rather than silently rejecting.
    """
    from app.validation.validators.numeric_grounding_validator import _normalize_unit

    assert _normalize_unit("DZD") == "dzd"
    assert _normalize_unit("XYZ") == ""
    assert _normalize_unit("and") == ""
    assert _normalize_unit("Case Credits") == "cc"
    assert _normalize_unit("$") == "usd"


# Adjacency alone leaves holes, all of them raised in review: a bare source
# figure beside an answer that invents a currency, a unit stated once in a
# table header rather than next to every figure, and a code no vocabulary
# lists. A claim's unit must also appear somewhere in the source.
_ALGERIA_WITH_UNITS = "Forever Algeria. Delivery Cost: 900 DZD. Minimum order size FBO: 0,200CC."
_ALGERIA_BARE = "Forever Algeria. Delivery Cost: 900. Minimum order size FBO: 0,200CC."
_ALGERIA_HEADER = "Forever Algeria. All fees are stated in DZD. Delivery Cost: 900. Minimum order 5000."
_NEW_ZEALAND = "Forever New Zealand. Delivery Cost: $8 +gst ($9.20)."

UNIT_CONTRAST_CASES = [
    # A source that never states a currency cannot support one.
    (_ALGERIA_BARE, "The delivery cost for Algeria is 900 EUR.", False),
    (_ALGERIA_BARE, "The delivery cost for Algeria is 900.", True),
    # An unlisted code is still a code when the answer capitalises it.
    (_ALGERIA_WITH_UNITS, "The delivery cost for Algeria is 900 XYZ.", False),
    # The unit may be stated once, in a header, rather than beside each figure.
    (_ALGERIA_HEADER, "The delivery cost for Algeria is 900 DZD.", True),
    (_ALGERIA_HEADER, "The delivery cost for Algeria is 900 EUR.", False),
    (_ALGERIA_WITH_UNITS, "The delivery cost for Algeria is 900 DZD.", True),
]


@pytest.mark.parametrize("source,answer,should_be_grounded", UNIT_CONTRAST_CASES)
def test_a_claim_unit_must_exist_in_the_source(source, answer, should_be_grounded):
    """Raised in review: the first unit check was still permissive.

    It compared units only where the source happened to state one next to the
    figure, so a bare source number, a header-scoped unit and an unlisted code
    all passed unchecked.
    """
    document = _document(source, "Forever Algeria", "sponsoring-001-algeria")
    unsupported = [claim.number for claim in unsupported_numeric_claims(answer, [document])]
    assert (not unsupported) is should_be_grounded, unsupported


def test_a_dollar_answer_against_a_dollar_record_is_grounded():
    """The control against over-rejection: same currency, different notation."""
    document = _document(_NEW_ZEALAND, "Forever New Zealand", "sponsoring-048-new-zealand")
    answer = "The delivery cost for New Zealand is US$8."
    assert not [claim.number for claim in unsupported_numeric_claims(answer, [document])]


def test_an_unlisted_code_is_a_unit_only_when_the_answer_capitalises_it():
    """Source text is casefolded before matching, so case is only available on
    the answer side. A lowercase word must not become a currency."""
    from app.validation.validators.numeric_grounding_validator import _normalize_unit

    assert _normalize_unit("XYZ", allow_unlisted_code=True) == "xyz"
    assert _normalize_unit("xyz", allow_unlisted_code=True) == ""
    assert _normalize_unit("and", allow_unlisted_code=True) == ""
    assert _normalize_unit("XYZ") == ""
