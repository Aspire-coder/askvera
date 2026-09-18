"""Fragment audit (Phase 2, Lane D): abbreviation- and initial-triggered fragments
left by ``remove_unsupported_numeric_sentences``. Deterministic/local: pure
function calls against ``RetrievedDocument`` stubs, no model or network call.

``remove_unsupported_numeric_sentences`` (owned by Lane C:
``app/validation/validators/numeric_grounding_validator.py``) finds sentence
boundaries with a bare ``[.!?](?=\\s|$)`` search, guarded only against a
letter-dot-letter-dot run such as "e.g." or "U.S." (two or more repeats). A
single abbreviation like "approx.", "ca." or "Nr.", or an initial like "J.",
is not that shape, so the period after it is read as the end of the
sentence. When the unsupported number that follows is removed, the
abbreviation is left standing alone as the "sentence" before it - the same
defect class as the already-fixed "09.00" decimal-time fragment
(tracker: MULTIPART-001 / Fable review 2026-09-18), reproduced here on
abbreviations instead of decimals.

Each ``xfail`` below is a confirmed defect in a file Lane D does not own.
The fix - swap the ad-hoc boundary regex for ``utils.sentence_spans`` - is a
in ``docs/conversation-quality/phase2/patches/laneD-numeric-grounding-validator.patch``, for
the coordinator or Lane C to apply.
"""

from __future__ import annotations

import pytest

from app.retrieval.models import RetrievedDocument
from app.validation.validators.numeric_grounding_validator import remove_unsupported_numeric_sentences


def _document(content: str) -> RetrievedDocument:
    return RetrievedDocument(
        id="d1", title="t", content=content, source="s", score=1.0, metadata={}
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "owned by Lane C (app/validation/validators/numeric_grounding_validator.py); "
        "patch at docs/conversation-quality/phase2/patches/laneD-numeric-grounding-validator.patch"
    ),
)
def test_removing_an_unsupported_figure_after_approx_does_not_orphan_the_abbreviation() -> None:
    answer = "The fee is approx. 999 USD for this tier. Payment methods accepted: cash."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, [_document("Payment methods accepted: cash.")]
    )
    assert removed == ["999"]
    # Before the fix: "The fee is approx. Payment methods accepted: cash." -
    # a dangling "approx." with nothing after it. The whole first sentence,
    # abbreviation included, must go with the number it introduced.
    assert "approx." not in repaired
    assert repaired == "Payment methods accepted: cash."


@pytest.mark.xfail(
    strict=True,
    reason=(
        "owned by Lane C (app/validation/validators/numeric_grounding_validator.py); "
        "patch at docs/conversation-quality/phase2/patches/laneD-numeric-grounding-validator.patch"
    ),
)
def test_removing_an_unsupported_figure_after_nr_does_not_orphan_the_abbreviation() -> None:
    answer = "See policy Nr. 999 for the fee schedule. Payment methods accepted: cash."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, [_document("Payment methods accepted: cash.")]
    )
    assert removed == ["999"]
    assert repaired == "Payment methods accepted: cash."


@pytest.mark.xfail(
    strict=True,
    reason=(
        "owned by Lane C (app/validation/validators/numeric_grounding_validator.py); "
        "patch at docs/conversation-quality/phase2/patches/laneD-numeric-grounding-validator.patch"
    ),
)
def test_removing_an_unsupported_figure_after_initials_does_not_orphan_the_name() -> None:
    answer = "Contact J. R. Smith about the 999 USD fee. Payment methods accepted: cash."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, [_document("Payment methods accepted: cash.")]
    )
    assert removed == ["999"]
    # Before the fix: "Contact J. R. Payment methods accepted: cash." - the
    # name is severed from the sentence that named it.
    assert "Contact J. R." not in repaired
    assert repaired == "Payment methods accepted: cash."


def test_negative_control_a_grounded_neighbour_sentence_survives_untouched() -> None:
    """The correct neighbouring sentence, unrelated to the abbreviation, is kept whole."""
    answer = "The fee is approx. 999 USD for this tier. Payment methods accepted: cash."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, [_document("Payment methods accepted: cash.")]
    )
    assert repaired.endswith("Payment methods accepted: cash.")


def test_negative_control_a_legitimate_sentence_break_still_removes_cleanly() -> None:
    """No abbreviation involved: the existing behaviour (whole-sentence removal) is unaffected."""
    answer = "The minimum order is 999 USD. Payment methods accepted: cash."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, [_document("Payment methods accepted: cash.")]
    )
    assert removed == ["999"]
    assert repaired == "Payment methods accepted: cash."
