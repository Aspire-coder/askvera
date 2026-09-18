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


# --- Fable Phase 2 review corrections -------------------------------------
#
# Findings 1 and 4: a bare newline was not a unit boundary unless preceded by
# terminal punctuation, and a lone capital-letter-plus-dot ("C.", "A.", "No.")
# was always read as an abbreviation/initial regardless of what followed it.
# See docs/conversation-quality/phase2/FRAGMENT_AUDIT.md for the full writeup.


def test_bare_newline_is_a_boundary_even_with_no_preceding_punctuation() -> None:
    """No "." "!" or "?" appears anywhere in this text; only the newlines mark units."""
    text = "Telephone Office: +254 20 2026869\nEmail: info@foreverea.com\nWebsite: www.foreverea.com"
    assert split_sentences(text) == [
        "Telephone Office: +254 20 2026869",
        "Email: info@foreverea.com",
        "Website: www.foreverea.com",
    ]


def test_bare_newline_boundary_does_not_split_a_url_or_email_across_lines() -> None:
    """A newline is a real boundary, but it never falls INSIDE a protected email/URL span."""
    text = "Contact support@example.com\nfor help."
    assert split_sentences(text) == ["Contact support@example.com", "for help."]


def test_heading_line_is_its_own_unit_and_does_not_swallow_the_next_line() -> None:
    text = "## Bonus\nDistributors receive a bonus."
    assert split_sentences(text) == ["## Bonus", "Distributors receive a bonus."]


def test_bullet_lines_are_each_their_own_unit() -> None:
    text = "- First claim here.\n- Second claim here."
    assert split_sentences(text) == ["- First claim here.", "- Second claim here."]


def test_lone_initial_before_a_period_is_an_ordinary_sentence_end() -> None:
    """A single "C." or "A." with no second initial nearby is a real sentence end -
    not part of a "J. R. Smith"-style chain. Fable Phase 2 review, finding 4:
    the earlier, blanket single-letter rule merged "Take Vitamin C." into
    whatever sentence followed it."""
    assert split_sentences("Take Vitamin C. Delivery takes 5 days.") == [
        "Take Vitamin C.",
        "Delivery takes 5 days.",
    ]
    assert split_sentences("Use Form A. Delivery takes 5 days.") == [
        "Use Form A.",
        "Delivery takes 5 days.",
    ]


def test_initial_chain_of_two_still_stays_whole_before_an_uppercase_name() -> None:
    """The positive control for the rule above: TWO OR MORE initials in a row are
    still read as one unit, unlike the lone-initial case."""
    assert split_sentences("Contact J. R. Smith about the order.") == [
        "Contact J. R. Smith about the order."
    ]


def test_plain_abbreviation_before_an_uppercase_word_is_terminal() -> None:
    """A plain abbreviation ("No", "Dec") is non-terminal only when a digit or a
    lowercase letter follows - never before an uppercase word. Fable Phase 2
    review, finding 4: "Is the fee refundable? No. Delivery takes 5 days."
    must split after "No.", not merge it into the sentence that follows."""
    assert split_sentences("Is the fee refundable? No. Delivery takes 5 days.") == [
        "Is the fee refundable?",
        "No.",
        "Delivery takes 5 days.",
    ]
    assert split_sentences("Send it by Dec. Delivery takes 5 days.") == [
        "Send it by Dec.",
        "Delivery takes 5 days.",
    ]


def test_plain_abbreviation_before_a_digit_or_lowercase_word_is_still_non_terminal() -> None:
    """Positive control: the forward-continuation half of the same rule is
    unchanged for the shapes it was designed for."""
    assert split_sentences("The fee is approx. 999 USD for this tier.") == [
        "The fee is approx. 999 USD for this tier."
    ]
    assert split_sentences("See policy Nr. 4.02 for the fee schedule.") == [
        "See policy Nr. 4.02 for the fee schedule."
    ]


def test_dotted_compound_abbreviation_protects_both_of_its_own_dots() -> None:
    """"e.g." and "z.B." each carry TWO dots (one internal, one final); both must
    stay non-terminal. Fable Phase 2 review, finding 4: these compound entries
    in ABBREVIATIONS could never actually match through the plain trailing-word
    lookup (which only ever sees the letters after the LAST internal dot), so
    they were previously protected only by accident, through the old blanket
    single-letter initial rule this fix removes."""
    text = "Bring identification, e.g. a passport, to the office."
    assert split_sentences(text) == [text]
    text_de = "Manche Unterlagen, z.B. ein Ausweis, werden benötigt."
    assert split_sentences(text_de) == [text_de]


def test_st_louis_now_splits_matching_base_behaviour_not_a_regression() -> None:
    """"St." before an uppercase proper noun ("St. Louis") now splits, per the
    coordinator's rule that a plain abbreviation is terminal before an
    uppercase word. This is NOT a regression versus base (commit dbc6a7a):
    base's own abbreviation guard, ``\\b(?:[^\\W\\d_]\\.){2,}``, only ever
    matched a run of single-LETTER-dot pairs ("J.R.", "z.B."), never a
    multi-letter word like "St" followed by one dot - so base already split
    "St. Louis" into two sentences; this restores that same behaviour rather
    than changing it."""
    assert split_sentences("Take the train to St. Louis for the conference.") == [
        "Take the train to St.",
        "Louis for the conference.",
    ]
