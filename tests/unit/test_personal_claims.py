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


# --- a category is an assumption or not, depending on what is known ---------
#
# Neither phrase is safe or unsafe by itself. An earlier version decided this
# from the wording alone and got both of these backwards: it deleted
# role-specific advice that the session supported, and kept an assumption the
# session contradicted.


def test_the_session_role_supports_the_category_it_declares() -> None:
    """An active_distributor session says the reader is an established one.

    So "As an existing FBO" states what is known and is the useful part of the
    answer. Deleting it takes away role-specific advice.
    """
    assert (
        unsupported_personal_claims(
            "As an existing FBO, you order 7 800DZD.", role="active_distributor"
        )
        == []
    )


def test_the_same_sentence_is_an_assumption_under_a_different_role() -> None:
    """The identical wording, and now nothing supports it."""
    assert unsupported_personal_claims(
        "As an existing FBO, you order 7 800DZD.", role="new_prospect"
    )


def test_a_category_no_session_declares_is_an_assumption_by_default() -> None:
    """No session role is a Preferred Customer, so nothing structural says so.

    Algeria's 0,200CC is a Preferred Customer's first order. Handing it to an
    active distributor under that heading is the wrong figure with a confident
    label on it.
    """
    assert unsupported_personal_claims(
        "As a Preferred Customer, you order 0,200CC.", role="active_distributor"
    )


def test_the_reader_saying_so_supports_it() -> None:
    """The context the session cannot supply, supplied by the reader."""
    assert (
        unsupported_personal_claims(
            "As a Preferred Customer, you order 0,200CC.",
            role="active_distributor",
            user_context="I am a Preferred Customer - what is the minimum order?",
        )
        == []
    )


def test_asking_about_a_category_is_not_being_in_it() -> None:
    """The near-miss that would make the context check meaningless.

    A question mentioning Preferred Customers is a question about a rule, not a
    statement about the person asking.
    """
    assert unsupported_personal_claims(
        "As a Preferred Customer, you order 0,200CC.",
        role="active_distributor",
        user_context="What is the minimum order for a Preferred Customer?",
    )


def test_no_context_makes_a_purchase_supportable() -> None:
    """Categories depend on context. Records never do.

    A session declares what someone is, never what they have done, so no role
    and no statement of their own can support this.
    """
    assert unsupported_personal_claims(
        "You have already placed your first order.",
        role="active_distributor",
        user_context="I am an existing FBO who has been ordering for years.",
    )


# --- rules, which are what the answer is for --------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        "You must order 2 CC as a first order.",
        "You can reach Manager by generating case credits.",
        "You have to order within 72 hours to validate the sponsorship.",
        "You may order any products from the price list.",
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


def test_a_rule_stated_of_a_category_is_not_a_claim_about_anyone() -> None:
    """Quoting a rule for a category is not placing the reader in it.

    "Preferred Customers must place a first order of 0,200CC" is how a policy
    answer covers a category without addressing the reader as one, and it needs
    no context at all.
    """
    assert unsupported_personal_claims(
        "Preferred Customers must place a first order of 0,200CC.",
        role="active_distributor",
    ) == []
    assert unsupported_personal_claims(
        "New FBOs order 0,200CC as a first order.", role="active_distributor"
    ) == []


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


# --- removal must not take the qualification with the assumption ------------


def test_a_removal_that_would_gut_the_answer_is_refused() -> None:
    """Repair must not leave something worse than a refusal.

    Removing the only sentence carrying a figure leaves "Payment is by bank
    transfer", which cannot answer a question about an amount. Presenting that
    as the answer is worse than saying the documents were not enough.
    """
    answer = (
        "As a Preferred Customer, you order 0,200CC as a first order. "
        "Payment is by bank transfer."
    )

    repaired, removed = remove_unsupported_personal_claims(
        answer, role="active_distributor"
    )

    assert removed == []
    assert repaired == answer
    assert unsupported_personal_claims(answer, role="active_distributor"), (
        "the claim is still reported, so the answer is refused rather than delivered"
    )


def test_a_removal_is_allowed_when_the_condition_survives_elsewhere() -> None:
    """The control for the guard above, so it does not simply block every repair."""
    answer = (
        "As a Preferred Customer, you order 0,200CC as a first order. "
        "The first order minimum for a Preferred Customer is 0,200CC."
    )

    repaired, removed = remove_unsupported_personal_claims(
        answer, role="active_distributor"
    )

    assert removed == ["As a Preferred Customer, you order 0,200CC as a first order."]
    assert "first order minimum for a Preferred Customer is 0,200CC" in repaired


def test_a_claim_carrying_no_condition_is_still_removed() -> None:
    """The guard is about conditions, not about making removal impossible."""
    answer = "You are currently a Manager. The minimum order size is 2 CC."

    repaired, removed = remove_unsupported_personal_claims(answer)

    assert removed == ["You are currently a Manager."]
    assert repaired == "The minimum order size is 2 CC."


# --- what the reader said may be used, never presented as verified ----------


STATED_PURCHASE = "I placed my first order yesterday - what is the minimum for my next one?"


def test_a_fact_the_reader_supplied_may_be_used() -> None:
    """Repeating what someone told you is not inventing it.

    An answer that explains the rule using their own statement is more useful
    than one that refuses to acknowledge they said anything.
    """
    assert (
        unsupported_personal_claims(
            "You have already placed your first order, so the minimum is 7 800DZD.",
            role="active_distributor",
            user_context=STATED_PURCHASE,
        )
        == []
    )


def test_the_same_sentence_without_the_statement_is_invented() -> None:
    assert unsupported_personal_claims(
        "You have already placed your first order, so the minimum is 7 800DZD.",
        role="active_distributor",
        user_context="What is the minimum order?",
    )


@pytest.mark.parametrize(
    "answer",
    [
        "Our records show you placed your first order yesterday.",
        "Your account shows you have already ordered.",
        "According to your records, you placed your first order yesterday.",
        "I can confirm that you placed your first order yesterday.",
    ],
)
def test_claiming_to_have_verified_it_is_never_supported(answer: str) -> None:
    """The distinction the reader's statement cannot rescue.

    They told us; nothing checked it. Saying we checked is a different claim
    and a worse one, so it stays unsupported however precisely it matches what
    they said.
    """
    assert unsupported_personal_claims(
        answer, role="active_distributor", user_context=STATED_PURCHASE
    ) == [answer]


def test_a_claim_going_beyond_what_was_said_is_still_invented() -> None:
    """Corroboration covers what they said, not what can be inferred from it."""
    assert unsupported_personal_claims(
        "You have already sponsored three people, so you qualify.",
        role="active_distributor",
        user_context=STATED_PURCHASE,
    )


# --- a role declared earlier survives the follow-up turn --------------------


def test_a_role_declared_in_an_earlier_turn_still_counts() -> None:
    """The current message alone loses it.

    "I'm a Preferred Customer" then "and the minimum order?" is a conversation
    where the role was declared once. Reading only the latest message would
    call the answer's use of that role an assumption the reader never made.
    """
    conversation = "I'm a Preferred Customer\nAnd what is the minimum order?"

    assert (
        unsupported_personal_claims(
            "As a Preferred Customer, you order 0,200CC as a first order.",
            role="active_distributor",
            user_context=conversation,
        )
        == []
    )


def test_the_same_follow_up_without_the_earlier_turn_is_an_assumption() -> None:
    """The control: it is the earlier turn doing the work, not the phrasing."""
    assert unsupported_personal_claims(
        "As a Preferred Customer, you order 0,200CC as a first order.",
        role="active_distributor",
        user_context="And what is the minimum order?",
    )


def test_the_orchestrator_reads_prior_turns_not_only_this_one() -> None:
    """Asserted against the orchestrator, because the helper cannot know.

    `_reader_statements` is what carries the earlier turn in, and a validator
    given only `body.message` would be correct in isolation and wrong in a
    conversation.
    """
    from app.orchestrator.chat_orchestrator import AIOrchestrator
    from utils.validators import ChatRequest

    orchestrator = AIOrchestrator()
    body = ChatRequest(
        message="And what is the minimum order?",
        sessionId="s",
        country="US",
        language="en",
        role="active_distributor",
    )
    history = "user: I'm a Preferred Customer\nassistant: Which market?"

    statements = orchestrator._reader_statements(body, history)

    assert "Preferred Customer" in statements
    assert "And what is the minimum order?" in statements
    assert "assistant" not in statements, "only what the reader said"


# --- what the paid comparison found -----------------------------------------
#
# Run 2026-09-09 against c5391bb and 40932ce on six cases. The candidate turned
# two working Algeria answers into refusals, and the answers it refused really
# did contain invented claims. The detection was right; three things about the
# response were wrong. These are the exact captured answers.


ALGERIA_REPEAT_Q = "In Algeria, what is the minimum order size after my first purchase?"
ALGERIA_REPEAT_A = (
    "# Minimum Order Size After First Purchase in Algeria After your first purchase as an "
    "FBO in Algeria, the FBO minimum order size is **5,000 DZD ($43)**. This applies to all "
    "FBOs following their initial order. For context, your first order as a Preferred "
    "Customer requires 0.200 CC (equivalent to 7,800 DZD or $60)."
)
ALGERIA_ROLE_Q = "I am already an FBO in Algeria. What is my minimum order now?"
ALGERIA_ROLE_A = (
    "As an active FBO in Algeria, your minimum order is the equivalent of 5,000 DZD ($43) "
    "after your first purchase. Your first order as a Preferred Customer was 0.200 CC "
    "(7,800 DZD / $60). Once you have completed that initial order, subsequent orders "
    "follow the lower minimum of 5,000 DZD ($43)."
)


def test_a_decimal_does_not_end_a_sentence() -> None:
    """The first defect: "0.200 CC" was split into "0." and "200 CC".

    A claim was reported as a fragment, and a repair would have left the stray
    "200 CC (equivalent to 7,800 DZD or $60)." behind in the answer. The
    splitter now comes from utils.qualifications, which guards the decimal.
    """
    from utils.personal_claims import _sentences

    for answer in (
        "The first order is 0.200 CC. The next is 5,000 DZD.",
        "The first order is 0,200CC. The next is 7 800DZD.",
    ):
        parts = _sentences(answer)
        assert len(parts) == 2
        assert not any(part.strip() in {"0.", "0,"} for part in parts)


@pytest.mark.parametrize(
    "answer",
    [
        "After your first purchase, the FBO minimum order size is 5,000 DZD.",
        "Following your first order, the lower minimum applies.",
        "Once you have placed your first order, the lower minimum applies.",
    ],
)
def test_a_stage_a_rule_applies_at_is_not_a_claim_about_the_reader(answer: str) -> None:
    """The second defect: a condition read as a personal claim.

    "After your first purchase, the minimum is..." names the stage a rule
    applies at and asserts nothing about whether this reader has reached it.
    That is how the records phrase the rule and how an answer should repeat it.
    """
    assert unsupported_personal_claims(answer, role="active_distributor") == []


def test_the_same_words_without_the_preposition_are_a_claim() -> None:
    """The control: it is the preposition doing the work, not the noun."""
    assert unsupported_personal_claims(
        "Your first order was 0.200 CC.", role="active_distributor"
    )


def test_a_figure_leaving_with_its_condition_is_not_a_reason_to_refuse() -> None:
    """The third defect, and the one that cost the reader the whole answer.

    The removed sentence takes both the claim and the 0.200 CC figure it
    qualifies. Nothing is left dangling, and the answer's own rule - 5,000 DZD
    after the first purchase - is untouched and still answers the question. The
    earlier guard refused this repair to protect a condition that was leaving
    anyway, and the reader got a refusal instead of a correct answer.
    """
    repaired, removed = remove_unsupported_personal_claims(
        ALGERIA_REPEAT_A, role="active_distributor", user_context=ALGERIA_REPEAT_Q
    )

    assert removed == [
        "For context, your first order as a Preferred Customer requires 0.200 CC "
        "(equivalent to 7,800 DZD or $60)."
    ]
    assert "0.200" not in repaired
    assert "5,000 DZD ($43)" in repaired
    assert "after your first purchase" in repaired.casefold()


def test_the_role_case_loses_the_figure_its_expectation_forbids() -> None:
    """The other captured answer, whose fixture forbids 0.200 for this reader.

    An existing FBO is being told a Preferred Customer's first-order figure.
    Repair removes exactly that sentence and leaves the rule that applies.
    """
    repaired, removed = remove_unsupported_personal_claims(
        ALGERIA_ROLE_A, role="active_distributor", user_context=ALGERIA_ROLE_Q
    )

    assert removed == ["Your first order as a Preferred Customer was 0.200 CC (7,800 DZD / $60)."]
    assert "0.200" not in repaired
    assert "5,000 DZD ($43)" in repaired


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        (
            "What is the delivery cost for orders in Algeria?",
            "The delivery cost for orders in Algeria is **900 DZD ($7.50)**.",
        ),
        (
            "What is the minimum order size for an FBO in France?",
            "For an FBO in France, there is **no minimum order size requirement**. However, a "
            "newly sponsored Preferred Customer must order a minimum of **150 EUR worth of "
            "products within 72 hours** to validate their sponsorship.",
        ),
    ],
)
def test_the_answers_that_were_already_correct_are_untouched(question: str, answer: str) -> None:
    """The controls from the same run, including the delivery-cost control."""
    assert (
        remove_unsupported_personal_claims(
            answer, role="active_distributor", user_context=question
        )
        == (answer, [])
    )


def test_an_orphaned_condition_still_refuses_the_repair() -> None:
    """The case the guard exists for, kept working.

    Here the condition leaves and the figure it qualifies stays, so the answer
    would be left stating 2 CC with nothing saying who it applies to.
    """
    answer = (
        "The minimum order size is 2 CC. Your first order as a Preferred Customer was 2 CC."
    )

    repaired, removed = remove_unsupported_personal_claims(answer, role="active_distributor")

    assert removed == []
    assert repaired == answer
