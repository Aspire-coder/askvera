"""Fragment audit (Phase 2, Lane D): a decimal figure inside the corrected
sentence truncates the "after sponsorship" replacement. Deterministic/local:
pure function call against a plain source string, no model or network call.

``correct_directory_source_contradictions`` (owned by Lane B:
``utils/directory_fields.py``) rewrites a generated "After sponsorship: ..."
sentence that contradicts the source's "no minimum order" statement. It finds
the end of that sentence with ``[^.\\n]+(?:\\.|$)`` - a bare "stop at the
first literal dot" search, the same shape of bug already fixed once in this
module for the "09.00" decimal-time fragment. When the generated sentence
itself contains a decimal figure ("...minimum order of 0.5 CC to place."),
the search stops at the dot inside "0.5" instead of the sentence's real end,
and the fixed replacement text is glued to whatever followed that decimal
point: "After sponsorship: there is no minimum order.5 CC to place."

The ``xfail`` below is a confirmed defect in a file Lane D does not own. The
fix - use ``utils.sentence_spans.sentence_boundaries`` for the real sentence
end - is a patch at
``docs/conversation-quality/phase2/patches/laneD-directory-fields-after-sponsorship.patch``,
for the coordinator or Lane B to apply.
"""

from __future__ import annotations

import pytest

from utils.directory_fields import correct_directory_source_contradictions

SOURCE = "After sponsorship: we don't have a minimum order."


@pytest.mark.xfail(
    strict=True,
    reason=(
        "owned by Lane B (utils/directory_fields.py); patch at "
        "docs/conversation-quality/phase2/patches/laneD-directory-fields-after-sponsorship.patch"
    ),
)
def test_a_decimal_figure_in_the_contradicted_sentence_does_not_truncate_the_fix() -> None:
    answer = "After sponsorship: we do not have a minimum order of 0.5 CC to place."
    corrected, changed = correct_directory_source_contradictions(answer, [SOURCE])
    assert changed is True
    # Before the fix: "After sponsorship: there is no minimum order.5 CC to
    # place." - the fixed replacement text fused with the decimal's tail.
    assert "order.5" not in corrected
    assert corrected == "After sponsorship: there is no minimum order."


def test_negative_control_a_neighbouring_sentence_survives_the_correction() -> None:
    """The correction must not disturb a correct sentence next to it."""
    answer = (
        "Before joining you need 2CC. "
        "After sponsorship: we do not have a minimum order of 0.5 CC to place. "
        "Payment methods accepted: cash."
    )
    corrected, changed = correct_directory_source_contradictions(answer, [SOURCE])
    assert changed is True
    assert corrected.startswith("Before joining you need 2CC.")
    assert corrected.endswith("Payment methods accepted: cash.")


def test_negative_control_no_decimal_still_corrects_cleanly() -> None:
    """Existing behaviour (no decimal figure involved) is unaffected."""
    answer = "After sponsorship: 500 DH minimum."
    corrected, changed = correct_directory_source_contradictions(answer, [SOURCE])
    assert changed is True
    assert corrected == "After sponsorship: there is no minimum order."
