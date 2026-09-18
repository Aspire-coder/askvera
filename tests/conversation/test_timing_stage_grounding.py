"""Phase 2, Lane C (conversation-quality project): a timing number must not move
between process stages.

Forever Living states several different clocks that share the same shape ("3
working days", "48 hours", "within 5 days"): how long delivery takes, how long
an application/registration/qualification takes to be approved, how long an
order takes to process, when a bonus or commission is paid, how long a bank
settlement takes to arrive, and a waiting period (a sponsor change, a
re-application) or a set of office/business hours. A model answer that keeps
the number but reports it for the wrong stage - "your bonus is paid within 3
working days" when the source states 3 working days for *delivery* - states a
real number from the record, so ordinary numeric grounding (is this number
anywhere in the source) does not catch it.

Design: no new post-generation editor. `_classify_stage` (added to
numeric_grounding_validator.py) reads cue terms from
config/timing_stage_vocabulary.py to name the one process stage a clause or
sentence is about, in the answer and in the matched source occurrence. Applied
only to a timing figure (one whose unit or period is a day/week/month/hour/year,
via the existing `_measures_agree` machinery), and only when both sides
classify to exactly one, different, stage: the occurrence is then treated as
not supporting the claim, same as any other numeric mismatch, and the existing
NUMERIC_CLAIM_UNGROUNDED path removes just that sentence on repair. Nothing
changes for a number with no time unit, or for a clause the classifier cannot
read confidently (see `_classify_stage`'s own docstring on that).

Every case below is reproduced first: the docstring records what
`unsupported_numeric_claims` returned on this repository's base code (a git
stash of this change), which is why the substitution was never caught before,
then what it returns now. Reproduced entirely offline, no model call.
"""

from types import SimpleNamespace

from app.validation.validators.numeric_grounding_validator import (
    remove_unsupported_numeric_sentences,
    unsupported_numeric_claims,
)


def _document(content: str, **metadata: object) -> SimpleNamespace:
    return SimpleNamespace(content=content, title="doc", id="doc", country="US", metadata=metadata)


def _claim_texts(answer: str, source: str) -> list[str]:
    return [claim.text for claim in unsupported_numeric_claims(answer, [_document(source)])]


# --- Delivery time borrowed as an approval time -----------------------------

def test_delivery_time_does_not_ground_an_approval_time_claim() -> None:
    """Before this change: `unsupported_numeric_claims` returned [] (the substitution
    passed unnoticed) because the answer and source shared enough surrounding
    words ("period", "months") for the pre-existing lexical fallback to accept
    it, even though "processed" (processing) and "waiting period" (waiting_period)
    name different stages. Confirmed by stashing this diff and re-running this
    exact case."""
    answer = "Your order will be processed within a period of 6 months."
    source = "There is a waiting period of 6 months before you may generate Case Credits again."
    assert _claim_texts(answer, source) == ["6"]


def test_delivery_time_grounds_a_delivery_time_claim() -> None:
    """Positive control: the same number, correctly kept to delivery, still passes."""
    answer = "There is a waiting period of 6 months before you may generate Case Credits again."
    source = "There is a waiting period of 6 months before you may generate Case Credits again."
    assert _claim_texts(answer, source) == []


# --- Waiting period borrowed as a processing time ---------------------------

def test_waiting_period_does_not_ground_a_processing_time_claim() -> None:
    """Before: []. "processed" and "waiting period" share no lexical overlap with
    the pre-existing fallback either, but here the answer borrows the exact
    figure and unit ("6 months") with a shared word ("months") that is not
    enough on its own (one shared word); this case is kept to show the
    substitution is caught purely by stage classification, not by an
    accidental lexical match."""
    answer = "Your order will be processed within 6 months."
    source = "After a change of sponsor, there is a waiting period of 6 months."
    assert _claim_texts(answer, source) == ["6"]


def test_waiting_period_grounds_a_waiting_period_claim() -> None:
    answer = "There is a waiting period of 6 months."
    source = "After a change of sponsor, there is a waiting period of 6 months."
    assert _claim_texts(answer, source) == []


# --- Bonus-payment date borrowed as bank settlement timing ------------------

def test_payment_date_does_not_ground_a_settlement_time_claim() -> None:
    """Before: []. "The bank transfer settlement period is 5 days" and "Your bonus
    payment date falls within a period of 5 days" share "period" and "days" -
    two words, enough for the pre-existing fallback to accept the figure even
    though the record states it for settlement, not payment."""
    answer = "Your bonus payment date falls within a period of 5 days."
    source = "The bank transfer settlement period is 5 days before the money is available."
    assert _claim_texts(answer, source) == ["5"]


def test_payment_date_grounds_a_payment_date_claim() -> None:
    answer = "Your bonus payment date is within 5 days of the close of the period."
    source = "The bonus payment date is within 5 days of the close of the period."
    assert _claim_texts(answer, source) == []


# --- "Within 48 hours" read as office/business hours ------------------------

def test_duration_does_not_ground_against_an_office_hours_count() -> None:
    """Before: []. "Your order is dispatched within a total of 48h" and "The office
    hours are a total of 48h a week" share "total" and "of" - two words - so the
    same number was accepted from an office-hours count. '48h' is exercised here
    on purpose: the number-unit form the brief calls out by name."""
    answer = "Your order is dispatched within a total of 48h."
    source = "The office hours are a total of 48h a week."
    assert _claim_texts(answer, source) == ["48"]


def test_duration_grounds_against_a_delivery_duration() -> None:
    answer = "Your order is delivered within 48 hours."
    source = "Orders are delivered within 48 hours of purchase."
    assert _claim_texts(answer, source) == []


# --- Non-timing numbers: behaviour must not change ---------------------------

def test_non_timing_number_is_unaffected_by_stage_classification() -> None:
    """A Case Credit count carries no time unit, so `_measures_agree` never reaches
    the stage check (claim_kind/claim_period are never a day/week/month/hour/year):
    behaviour is exactly what it was before this change, for a subject that is
    also unrelated to any covered stage."""
    answer = "Supervisor is achieved by generating 10 Open Group Case Credits within any Month."
    source = "Supervisor is achieved by generating a total of 10 Open Group Case Credits within any Month."
    assert _claim_texts(answer, source) == []


def test_currency_amount_is_unaffected_even_beside_stage_words() -> None:
    """A minimum-order amount stated for the correct role/market still grounds
    even though its sentence happens to name a stage word; the stage check
    only ever narrows a TIMING figure, never a currency one."""
    answer = "For FBOs, the minimum order size for delivery is 50 USD."
    source = "Minimum order size FBO: 50 USD."
    assert _claim_texts(answer, source) == []


# --- Numeric-format controls -------------------------------------------------

def test_hyphen_range_delivery_time_does_not_ground_an_approval_range() -> None:
    """Before: []. Answer and source share "working" and "days" (two words)."""
    answer = "Approval takes 3-5 working days."
    source = "Delivery takes 3-5 working days."
    assert _claim_texts(answer, source) == ["3-5"]


def test_hyphen_range_delivery_time_grounds_a_delivery_range() -> None:
    answer = "Delivery takes 3-5 working days."
    source = "Delivery takes 3-5 working days."
    assert _claim_texts(answer, source) == []


def test_en_dash_range_delivery_time_does_not_ground_an_approval_range() -> None:
    """The en dash notation ("3–5") the corpus also uses, not only a hyphen."""
    answer = "Approval takes 3–5 working days."
    source = "Delivery takes 3–5 working days."
    assert _claim_texts(answer, source) == ["3–5"]


def test_glued_hour_notation_delivery_does_not_ground_office_hours() -> None:
    """"48h" (a figure glued to its unit letter, no space) exercised again on its
    own, isolated from the office-hours wording used in the duration test above."""
    answer = "Your parcel is dispatched in 48h total."
    source = "The office hours are 48h total, Monday to Friday."
    assert _claim_texts(answer, source) == ["48"]


def test_comma_decimal_payment_date_does_not_ground_a_delivery_total() -> None:
    """Comma-decimal notation ("3,5"), which this corpus also writes for a
    fractional day count."""
    answer = "Your payment date total is 3,5 days."
    source = "The delivery total is 3,5 days."
    assert _claim_texts(answer, source) == ["3,5"]


def test_comma_decimal_payment_date_grounds_a_payment_date_total() -> None:
    answer = "Your payment date total is 3,5 days."
    source = "The payment date total is 3,5 days."
    assert _claim_texts(answer, source) == []


def test_french_working_days_phrase_delivery_does_not_ground_an_approval_claim() -> None:
    """"30 jours ouvrables" (30 working days), the French phrasing named in the
    brief, still classifies as a day-unit timing figure."""
    answer = "Approval takes 30 jours ouvrables."
    source = "Delivery takes 30 jours ouvrables."
    assert _claim_texts(answer, source) == ["30"]


def test_french_working_days_phrase_grounds_a_delivery_claim() -> None:
    answer = "Delivery takes 30 jours ouvrables."
    source = "Delivery takes 30 jours ouvrables."
    assert _claim_texts(answer, source) == []


# --- End-to-end: repair removes only the wrong-stage sentence ---------------

def test_repair_removes_only_the_wrong_stage_sentence_and_keeps_its_neighbours() -> None:
    """Before this change: both the correct delivery sentence and the wrong-stage
    approval sentence were removed (`unsupported_numeric_claims` returned two
    claims of "5", one for each), because subject binding for "Your delivery"
    happened to line up with the source's "Delivery" while "Your approval" fell
    back to the same lexical path and matched by accident of shared words - the
    stage was never checked at all, so nothing distinguished them once both
    passed. After this change, only the approval sentence -- which states the
    delivery number for a different stage -- is removed; the correctly-staged
    delivery sentence AND the unrelated currency sentence both survive intact.
    """
    answer = (
        "Your delivery takes 5 days. Your approval takes 5 days. "
        "The minimum order size is 50 USD."
    )
    source = "Delivery takes 5 days. The minimum order size is 50 USD."
    repaired, removed = remove_unsupported_numeric_sentences(answer, [_document(source)])
    assert removed == ["5"]
    assert repaired == "Your delivery takes 5 days. The minimum order size is 50 USD."
