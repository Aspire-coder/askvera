"""Fable Phase 2 review corrections to the timing-stage substitution check
(finding 3). Deterministic/local: pure function calls, no model or network call.

See docs/conversation-quality/phase2/FRAGMENT_AUDIT.md, "Fable Phase 2 review
corrections", for the full writeup. Three sub-findings, each reproduced first
and then fixed:

(a) BLOCKER-adjacent regression: bare "wait" in the English waiting_period cue
    list (and its bare-verb equivalents in every other language table) made
    "Please wait 3-5 working days for your parcel." classify as waiting_period,
    even though it is an ordinary, correct delivery answer. Fixed by removing
    the generic bare verb from every language's waiting_period tuple in
    config/timing_stage_vocabulary.py, keeping only phrases that name the
    waiting period itself ("waiting period", "must wait", "cooling-off", ...).
(b) DELIBERATE, kept: a bonus-payment date must not ground a bank-settlement
    time, and "processing" must not ground "approval" - both stay flagged.
    Pinned here so a future change does not casually loosen them back.
(c) GAP, now closed: a bracketed/parenthesised numeral ("five (5) working
    days") was never even extracted as a numeric claim (see
    `_is_structural_reference` in numeric_grounding_validator.py, which read
    ANY "(N)" as a footnote/citation marker), so it skipped the stage check
    entirely. Fixed by recognising a spelled-out number immediately before
    the parenthesised figure as a real claim, not a footnote.
"""

from __future__ import annotations

from app.retrieval.models import RetrievedDocument
from app.validation.validators.numeric_grounding_validator import (
    remove_unsupported_numeric_sentences,
    unsupported_numeric_claims,
)


def _document(content: str) -> RetrievedDocument:
    return RetrievedDocument(id="d1", title="t", content=content, source="s", score=1.0, metadata={})


def _claim_texts(answer: str, source: str) -> list[str]:
    return [claim.text for claim in unsupported_numeric_claims(answer, [_document(source)])]


# --- (a) "wait" is not a waiting_period cue on its own ----------------------


def test_wait_used_for_delivery_is_not_misread_as_a_waiting_period_answer() -> None:
    """Before the fix: `_claim_texts` returned ["3-5"] - the bare word "wait" in
    the answer classified it as waiting_period, while the source (no "wait"
    at all) classified as delivery, and the mismatch deleted a correct
    delivery answer. After the fix: the answer no longer classifies as
    waiting_period at all (no waiting-period-naming phrase is present), so
    the figure is compared as any ordinary delivery claim and grounds."""
    answer = "Please wait 3-5 working days for your parcel."
    source = "Delivery takes 3-5 working days."
    assert _claim_texts(answer, source) == []
    repaired, removed = remove_unsupported_numeric_sentences(answer, [_document(source)])
    assert removed == []
    assert repaired == answer


def test_specific_waiting_period_phrasing_is_still_caught_as_a_mismatch() -> None:
    """Positive control: removing the generic verb must not blunt the check
    entirely. "Must wait" is still a waiting_period cue, and a genuine
    waiting-period-for-delivery substitution is still rejected."""
    answer = "You must wait 3-5 working days before you can change sponsor."
    source = "Delivery takes 3-5 working days."
    assert _claim_texts(answer, source) == ["3-5"]


# --- (b) deliberate trade-offs, pinned ---------------------------------------


def test_bonus_payment_date_does_not_ground_a_settlement_time_deliberately_kept() -> None:
    """DELIBERATE, per the coordinator's brief: a bonus-payment date must not
    become a bank-arrival time, even though both sentences share "days" and
    "account"-adjacent wording. This must stay flagged as unsupported; do not
    loosen it to make this pass."""
    answer = "Your bonus is credited to your account within 15 days of month end."
    source = "Bonuses are paid within 15 days of month end."
    assert _claim_texts(answer, source) == ["15"]


def test_processing_time_does_not_ground_an_approval_time_deliberately_kept() -> None:
    """DELIBERATE, documented trade-off: "processing" and "approval" name
    related but different events, and a processing-time claim must not be
    grounded by a source that only states an approval time. This must stay
    flagged; do not loosen it to make this pass."""
    answer = "The application process takes 10 working days."
    source = "Applications are approved within 10 working days."
    assert _claim_texts(answer, source) == ["10"]


# --- (c) a bracketed/parenthesised numeral gets the same stage check --------


def test_bracketed_numeral_after_a_spelled_out_number_still_gets_the_stage_check() -> None:
    """Before the fix: `_claim_texts` returned [] - "(5)" was read as a footnote
    marker (`_is_structural_reference`) and never extracted as a claim at
    all, so the approval-borrows-delivery substitution went uncaught even
    though the exact same substitution written as a bare "5" was already
    caught. After the fix: the bracketed figure is extracted and stage-checked
    exactly like any other timing figure."""
    answer = "Approval takes five (5) working days."
    source = "Delivery takes five (5) working days."
    assert _claim_texts(answer, source) == ["5"]
    repaired, removed = remove_unsupported_numeric_sentences(answer, [_document(source)])
    assert removed == ["5"]
    assert repaired == ""


def test_bracketed_numeral_negative_control_still_grounds_when_the_stage_matches() -> None:
    """Positive control: the same bracketed shape, same stage on both sides,
    must still ground - the fix must not newly reject every bracketed figure."""
    answer = "Delivery takes five (5) working days."
    source = "Delivery takes five (5) working days."
    assert _claim_texts(answer, source) == []


def test_bracketed_numeral_still_ignored_as_a_footnote_without_a_spelled_out_number() -> None:
    """Negative control: an ordinary footnote/citation-style "(1)" with nothing
    spelled out in front of it is still ignored, exactly as before - this fix
    is scoped to the spelled-out-number-then-figure convention only."""
    answer = "Delivery takes 3 working days (1)."
    source = "Delivery takes 3 working days."
    assert _claim_texts(answer, source) == []
