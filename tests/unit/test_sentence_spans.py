"""Unit tests for utils.sentence_spans. Deterministic/local: pure functions, no I/O.

Each case in ``ADVERSARIAL_KEEP_WHOLE`` names a shape that a naive
``[.!?](?=\\s|$)`` boundary regex would wrongly split, and asserts the string
around it is never cut in half. ``REAL_BREAKS`` is the negative control: a
legitimate sentence break must still split, so a fix for the adversarial
cases cannot be "never split anything".
"""

from __future__ import annotations

import pytest

from utils.sentence_spans import iter_sentences, sentence_boundaries, split_sentences


# Each text must be returned as exactly ONE sentence: the internal "." (or
# "!"/"?") must never be read as a boundary.
ADVERSARIAL_KEEP_WHOLE = [
    ("decimal time", "Business hours are 09.00 am - 19.00 pm."),
    ("decimal time range without meridiem", "Office hours are 09.00-17.00 daily."),
    ("small decimal", "The exchange rate is roughly 3.5 percent."),
    ("comma-decimal currency", "The fee is 1 234,56 kr for the order."),
    ("dollar decimal currency", "The total comes to $1,000.00 for this order."),
    ("euro comma currency", "The price is €50,00 for members."),
    ("english abbreviation e.g.", "Bring identification, e.g. a passport, to the office."),
    ("english abbreviation i.e.", "Orders ship same day, i.e. within 24 hours, when paid by noon."),
    ("english abbreviation approx.", "The fee is approx. 999 USD for this tier."),
    ("english abbreviation etc.", "Bring ID, proof of address, etc. to the appointment."),
    ("german abbreviation z.B.", "Manche Unterlagen, z.B. ein Ausweis, werden benötigt."),
    ("german abbreviation bzw.", "Der Preis liegt bei 50 bzw. 60 USD je nach Rolle."),
    ("french abbreviation p. ex.", "Certains documents, p. ex. un passeport, sont requis."),
    ("clause reference", "Under clause 16.02(k), the fee is waived."),
    ("section reference", "See section 4.02 for the schedule."),
    ("numbered subclause", "As stated in 16.02(k), the minimum is 999 USD."),
    ("initials", "Contact J. R. Smith about the order."),
    ("email address", "Email support at care.team@example.co.uk for help."),
    ("url with path and query", "See https://example.com/policy/a.b?c=d for details."),
    ("url trailing in sentence", "Visit www.example.com/terms.html before ordering."),
    ("phone number with dot-like grouping", "Call +254 20 2026869 or +254 20 2026873 for help."),
    ("parenthetical phone range", "Call the office at (555) 123-4567 for help."),
    ("nr abbreviation", "See policy Nr. 4.02 for the fee schedule."),
    ("ellipsis mid-thought", "The minimum order is... still being confirmed."),
]

# Each text must split into exactly the given sentence list: a genuine
# sentence break must still work even after the adversarial cases above are
# protected.
REAL_BREAKS = [
    (
        "Minimum order size FBO: $100 worth of products when joining. "
        "Business hours are 09.00 am - 19.00 pm. "
        "Payment methods accepted: Mpesa.",
        [
            "Minimum order size FBO: $100 worth of products when joining.",
            "Business hours are 09.00 am - 19.00 pm.",
            "Payment methods accepted: Mpesa.",
        ],
    ),
    (
        "The fee is approx. 999 USD. Payment methods accepted: cash.",
        ["The fee is approx. 999 USD.", "Payment methods accepted: cash."],
    ),
    (
        "Contact J. R. Smith about the 999 USD fee. Payment methods accepted: cash.",
        ["Contact J. R. Smith about the 999 USD fee.", "Payment methods accepted: cash."],
    ),
    (
        'Is that correct? "Yes, it is," she said.',
        ["Is that correct?", '"Yes, it is," she said.'],
    ),
    (
        "Are you sure?! That changes everything.",
        ["Are you sure?!", "That changes everything."],
    ),
    (
        "The minimum order is 50 USD.\nDelivery costs 5 USD.",
        ["The minimum order is 50 USD.", "Delivery costs 5 USD."],
    ),
]


@pytest.mark.parametrize("label,text", ADVERSARIAL_KEEP_WHOLE, ids=[label for label, _ in ADVERSARIAL_KEEP_WHOLE])
def test_adversarial_shape_is_never_split(label: str, text: str) -> None:
    sentences = split_sentences(text)
    assert sentences == [text], f"{label}: {sentences!r}"


@pytest.mark.parametrize("text,expected", REAL_BREAKS)
def test_real_sentence_breaks_still_split(text: str, expected: list[str]) -> None:
    assert split_sentences(text) == expected


def test_iter_sentences_spans_cover_the_source_exactly() -> None:
    text = "The fee is approx. 999 USD. Payment methods accepted: cash."
    spans = iter_sentences(text)
    assert "".join(span.text for span in spans) == text
    assert [text[start:end] for _, start, end in spans] == [span.text for span in spans]


def test_no_boundary_inside_a_decimal_number() -> None:
    text = "Business hours are 09.00 am - 19.00 pm."
    boundaries = sentence_boundaries(text)
    dot_index = text.index("09.00") + 2
    assert dot_index + 1 not in boundaries


def test_boundary_after_a_real_sentence_end() -> None:
    text = "The minimum order is 50 USD. Delivery costs 5 USD."
    boundaries = sentence_boundaries(text)
    assert text.index(".") + 1 in boundaries


def test_empty_text_returns_no_sentences() -> None:
    assert split_sentences("") == []
    assert iter_sentences("") == []


def test_single_sentence_no_trailing_punctuation() -> None:
    assert split_sentences("No terminal punctuation here") == ["No terminal punctuation here"]
