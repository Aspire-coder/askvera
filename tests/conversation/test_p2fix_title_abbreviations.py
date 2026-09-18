"""Deterministic/local proof: independent re-review, finding 1 (title
abbreviations) and finding 2 (empty newline units), exercised through the
real callers that consume ``utils.sentence_spans`` rather than only through
that module's own unit tests. Pure function calls against
``RetrievedDocument`` stubs, no model or network call.

Finding 1: ``utils/sentence_spans.py``'s abbreviation rule (added by p2fix-1,
Fable Phase 2 review finding 4) made a plain abbreviation's "." terminal
before an uppercase word - correct for "No." and "Dec." ("Is the fee
refundable? No. Delivery takes 5 days." must split after "No.") but wrong for
personal/place TITLES, whose following capitalised word is the name the
title attaches to, not a new sentence. "Call Dr. Smith. Delivery takes 3
days." was wrongly split into "Call Dr." + "Smith. Delivery takes 3 days.",
and the exact same shape corrupts
``app/validation/validators/numeric_grounding_validator.py``'s
``remove_unsupported_numeric_sentences``: deleting an unsupported number next
to a directory contact left "Contact Dr." standing alone as the answer, with
the name and the sentence that named it discarded. Fixed by
``TITLE_ABBREVIATIONS``, a closed set (Dr, Mr, Mrs, Ms, Prof, St, Mt, Sr, Jr
and the configured-language equivalents) whose period is non-terminal before
a capitalised word specifically; every other abbreviation keeps p2fix-1's
terminal-before-uppercase rule.

See docs/conversation-quality/phase2/FRAGMENT_AUDIT.md for the full
before/after table and the "St." Saint-vs-Street trade-off this fix accepts.
"""

from __future__ import annotations

from app.retrieval.models import RetrievedDocument
from app.validation.validators.numeric_grounding_validator import remove_unsupported_numeric_sentences
from utils.sentence_spans import sentence_boundaries, split_sentences


def _document(content: str) -> RetrievedDocument:
    return RetrievedDocument(id="d1", title="t", content=content, source="s", score=1.0, metadata={})


# --- Finding 1: a title abbreviation does not orphan the name it introduces -


def test_removing_an_unsupported_figure_after_a_title_does_not_orphan_the_name() -> None:
    """The reviewer's own repro, reproduced through the real numeric-repair
    caller: deleting the unsupported "999" must take the whole sentence that
    introduced it - "Contact Dr." - with it, not leave the title stranded."""
    answer = "Contact Dr. Smith about the 999 USD fee. Payment methods accepted: cash."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, [_document("Payment methods accepted: cash.")]
    )
    assert removed == ["999"]
    # Before this fix: "Contact Dr. Payment methods accepted: cash." - "Dr."
    # read as its own sentence end, severing the title from the name.
    assert "Contact Dr." not in repaired
    assert repaired == "Payment methods accepted: cash."


def test_removing_an_unsupported_figure_after_a_street_title_does_not_orphan_it() -> None:
    """Same shape, "St." (Saint) directly before a place name."""
    answer = "The office is near St. Louis and charges a 999 USD surcharge. Payment methods accepted: cash."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, [_document("Payment methods accepted: cash.")]
    )
    assert removed == ["999"]
    assert "near St." not in repaired
    assert repaired == "Payment methods accepted: cash."


def test_negative_control_a_non_title_abbreviation_still_orphans_correctly_ie_not_at_all() -> None:
    """Positive/negative control together: "No." and "Dec." are NOT titles, so
    they keep p2fix-1's behaviour (terminal before an uppercase word) - the
    sentence boundary lands right after them, same as before this fix."""
    answer = "Is the fee refundable? No. Delivery takes 5 days for a 999 USD order."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, [_document("Is the fee refundable? No. Delivery takes 5 days.")]
    )
    assert removed == ["999"]
    # The whole "Delivery ... 999 USD order." sentence goes with the number,
    # exactly as it would for any other unsupported claim; "No." (not a
    # title) is still correctly read as its own, separate sentence rather
    # than being swallowed into the deletion, which is the behaviour this
    # control exists to protect.
    assert repaired == "Is the fee refundable? No."


def test_title_before_uppercase_name_stays_joined_to_its_own_sentence() -> None:
    """Direct proof at the ``split_sentences`` layer for every title named in
    finding 1, English and its configured-language equivalents: the title
    stays attached to the name it introduces (one sentence, not split at the
    title's own "."), while the text still correctly splits into its TWO
    real sentences overall."""
    cases = [
        ("Call Dr. Smith. Delivery takes 3 days.", "Call Dr. Smith."),
        ("Ask Mr. Jones. Delivery takes 3 days.", "Ask Mr. Jones."),
        ("Contact Mrs. Kim. Delivery takes 3 days.", "Contact Mrs. Kim."),
        ("Ask Ms. Patel. Delivery takes 3 days.", "Ask Ms. Patel."),
        ("Contact Prof. Lee. Delivery takes 3 days.", "Contact Prof. Lee."),
        ("Ask Hr. Müller. Delivery takes 3 days.", "Ask Hr. Müller."),
        ("Ask Mme. Dupont. Delivery takes 3 days.", "Ask Mme. Dupont."),
        ("Contact Sra. Lopez. Delivery takes 3 days.", "Contact Sra. Lopez."),
        ("Ask Dott. Rossi. Delivery takes 3 days.", "Ask Dott. Rossi."),
    ]
    for text, first_sentence in cases:
        sentences = split_sentences(text)
        assert sentences == [first_sentence, "Delivery takes 3 days."], (text, sentences)


def test_non_title_abbreviation_before_uppercase_word_still_splits() -> None:
    """Negative control: "No." and "Dec." are excluded from the closed title
    set on purpose, so they still split before an uppercase word - the exact
    behaviour finding 4 introduced and finding 1 leaves untouched."""
    assert split_sentences("See policy No. Delivery takes 5 days.") == [
        "See policy No.",
        "Delivery takes 5 days.",
    ]
    assert split_sentences("Ship it by Dec. Delivery takes 5 days.") == [
        "Ship it by Dec.",
        "Delivery takes 5 days.",
    ]


def test_main_st_street_ending_a_sentence_is_a_documented_known_limitation() -> None:
    """The accepted trade-off: "St." stays non-terminal before a capitalised
    word even when it means "Street" ending a sentence, because "St.
    <Capitalised City>" (Saint) is the shape actually seen in directory data.
    Documented here, not silently regressed."""
    assert split_sentences("The clinic is on Main St. Delivery takes 3 days.") == [
        "The clinic is on Main St. Delivery takes 3 days."
    ]


# --- Finding 2: an empty newline unit does not appear as its own boundary --


def test_no_empty_unit_between_a_period_and_the_newline_that_follows_it() -> None:
    assert sentence_boundaries("A.\nB.") == [2, 5]
    assert split_sentences("A.\nB.") == ["A.", "B."]


def test_directory_answer_with_period_then_newline_has_no_blank_unit() -> None:
    """A realistic directory-answer shape: a title-abbreviated sentence
    immediately followed by a label line - the period and the newline are
    adjacent, so this also exercises finding 2 in combination with finding 1."""
    text = "Contact Dr. Smith.\nTelephone: +254 20 2026869"
    assert split_sentences(text) == [
        "Contact Dr. Smith.",
        "Telephone: +254 20 2026869",
    ]
