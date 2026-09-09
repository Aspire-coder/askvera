"""Telling a reader what their own record says, when we hold no record.

An Algeria answer in the pilot described the reader's purchase history. There
is no purchase history anywhere in this system: a session carries a market, a
language and a declared role, and the documents describe rules for categories
of people.

The line drawn is between a rule addressed to the reader and a record about
them. Most of these tests are negative controls, because the way this fails is
by deleting ordinary sentences from correct answers.
"""

from __future__ import annotations

import pytest

from app.validation.models import (
    ValidationContext,
    ValidationResult,
    ValidationSeverity,
)
from app.validation.validators import PersonalHistoryValidator
from utils.personal_claims import (
    remove_unsupported_personal_claims,
    unsupported_personal_claims,
)
from app.response.models import ChatResponse


# --- records we do not have -------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        "You have already placed your first order, so the minimum is 7 800DZD.",
        "You ordered last month, so no minimum applies.",
        "Since you ordered in March, the higher figure applies.",
        "Your previous orders qualify you for the bonus.",
        "Your purchase history shows three orders.",
        "You are currently a Manager.",
        "You have qualified for the incentive.",
    ],
)
def test_a_claim_about_this_reader_is_reported(answer: str) -> None:
    assert unsupported_personal_claims(answer) == [answer]


def test_an_assumed_category_is_a_claim_about_the_reader() -> None:
    """The Preferred Customer / existing FBO distinction, which changes the figure.

    Algeria's 0,200CC is a Preferred Customer's first order. Telling an
    existing FBO that it is theirs is the wrong number, and the sentence that
    does it is an assumption about who they are.
    """
    assert unsupported_personal_claims("As an existing FBO, you order 7 800DZD.")


# --- rules, which are what the answer is for --------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        "You must order 2 CC as a first order.",
        "You can reach Manager by generating case credits.",
        "You have to order within 72 hours to validate the sponsorship.",
        "You may order any products from the price list.",
        "As a Preferred Customer, you order 0,200CC as a first order.",
        "Preferred Customers must place a first order of 0,200CC.",
        "The minimum order size is 2 CC.",
        "New FBOs have already been assigned a sponsor at registration.",
    ],
)
def test_a_rule_addressed_to_the_reader_is_left_alone(answer: str) -> None:
    """The negative controls. Deleting these takes the answer away."""
    assert unsupported_personal_claims(answer) == []


def test_a_conditional_claims_nothing_about_the_reader() -> None:
    """"If you have already ordered" does not assert that they have.

    This is how a correct answer covers both branches of a rule, and it is the
    phrasing an over-eager check would delete first.
    """
    answers = [
        "If you have already placed a first order, the minimum is 7 800DZD.",
        "Whether you have ordered before determines which figure applies.",
        "Once you have placed a first order, the lower figure applies.",
    ]

    for answer in answers:
        assert unsupported_personal_claims(answer) == []


def test_a_stated_category_is_not_an_assumed_one() -> None:
    """"As a Preferred Customer" states which rule is being quoted.

    "As an existing FBO" asserts which one the reader is. The first is how a
    policy answer is written; only the second claims something.
    """
    assert unsupported_personal_claims("As a Preferred Customer, you order 0,200CC.") == []
    assert unsupported_personal_claims("As an existing FBO, you order 7 800DZD.")


# --- repair keeps the rest of the answer ------------------------------------


def test_only_the_offending_sentence_is_removed() -> None:
    answer = (
        "You have already placed your first order. The minimum order size for an "
        "FBO in Algeria is 7 800DZD after the first purchase."
    )

    repaired, removed = remove_unsupported_personal_claims(answer)

    assert removed == ["You have already placed your first order."]
    assert repaired == (
        "The minimum order size for an FBO in Algeria is 7 800DZD after the first purchase."
    )


def test_an_answer_that_is_only_a_claim_repairs_to_nothing() -> None:
    """An empty repair is not delivered; the caller refuses instead."""
    repaired, removed = remove_unsupported_personal_claims("You are currently a Manager.")

    assert repaired == ""
    assert removed == ["You are currently a Manager."]


def test_an_answer_with_no_claim_is_returned_unchanged() -> None:
    answer = "The minimum order size is 2 CC.\n\nYou must order within 72 hours."

    assert remove_unsupported_personal_claims(answer) == (answer, [])


# --- the validator ----------------------------------------------------------


def _context(answer: str) -> ValidationContext:
    return ValidationContext(
        chat_response=ChatResponse(
            answer=answer,
            citations=[],
            suggestions=[],
            cards=[],
            confidence=0.9,
            metadata={},
            correlation_id="cid",
        ),
        model_response=None,
        retrieval_result=None,
        country="DZ",
        language="en",
        role="active_distributor",
        correlation_id="cid",
    )


def test_the_validator_reports_a_claim_as_critical() -> None:
    """Critical, because only critical findings reach the repair path."""
    result = ValidationResult()

    PersonalHistoryValidator().validate(
        _context("You have already placed your first order."), result
    )

    assert [issue.code for issue in result.issues] == ["PERSONAL_HISTORY_UNSUPPORTED"]
    assert result.issues[0].severity is ValidationSeverity.CRITICAL


def test_the_validator_is_silent_on_an_ordinary_answer() -> None:
    result = ValidationResult()

    PersonalHistoryValidator().validate(_context("The minimum order size is 2 CC."), result)

    assert result.issues == []


def test_the_repair_path_accepts_this_code() -> None:
    """Wired, not merely detected.

    The orchestrator repairs only critical findings it names. A code missing
    from that set would be detected and then refuse the whole answer, which is
    the failure mode this asserts against.
    """
    import inspect
    import re

    from app.orchestrator import chat_orchestrator

    source = inspect.getsource(chat_orchestrator.AIOrchestrator)
    source = re.sub(r"#.*", "", source)

    assert "PERSONAL_HISTORY_UNSUPPORTED" in source
    assert "remove_unsupported_personal_claims" in source


# --- follow-up turns must not import assumptions ----------------------------


def test_a_follow_up_does_not_acquire_a_history_from_its_own_wording() -> None:
    """A follow-up carries the earlier question forward, not a record.

    "What about after that?" is about the rule's next branch. An answer that
    turns it into "you have already ordered" has invented the reader's
    position in the sequence.
    """
    follow_up_answer = (
        "After the first purchase the minimum is 7 800DZD. You have already made "
        "that purchase."
    )

    repaired, removed = remove_unsupported_personal_claims(follow_up_answer)

    assert removed == ["You have already made that purchase."]
    assert repaired == "After the first purchase the minimum is 7 800DZD."


def test_a_non_english_answer_passes_through() -> None:
    """Recorded as a gap, not a claim of coverage.

    The patterns are English. A French answer inventing a purchase history is
    not caught, which leaves current behaviour; guessing at another language's
    grammar would delete correct sentences instead.
    """
    french = "Vous avez déjà passé votre première commande."

    assert unsupported_personal_claims(french) == []
