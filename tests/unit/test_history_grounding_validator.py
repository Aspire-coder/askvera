"""Tests for the history-is-not-evidence groundedness check.

Regression for the live failure (correlation ids
35aec7ae-7d03-4dba-9755-22b7b04e4d85 and 4cb3d453-9629-492d-81bd-5c1be4ddbf31):
a US session's third turn asked "Is this the whole contract or are there other
documents?", retrieval returned exactly one global sponsoring-directory
record, and the model answered from policy facts stated in an earlier turn's
history instead - quoting section 18.01(c) and listing sections 19, 20 and 21,
none of which this turn's evidence contains.

Canary fix (2026-09-25, chained-followup-market-continuity): the validator
now also requires ``conversation_history`` to actually cover a flagged
sentence, and never requires history to exist at all before that check can
even run - see ``history_grounding_validator``'s module docstring for the two
false-positive classes this closes. Every ``_context(...)`` call below that
exercises a genuine history-sourced-claim reproduction now also passes
``history=...``; the ones that must stay valid either pass no history at all
(turn 0) or history that does not itself state the sentence in question.
"""

from app.response.models import ChatResponse
from app.retrieval.models import RetrievalResult, RetrievedDocument
from app.validation.models import ValidationContext, ValidationResult
from app.validation.validators.history_grounding_validator import HistoryGroundingValidator

_DIRECTORY_RECORD = (
    "Sponsoring Directory - North America\n"
    "Country: United States\n"
    "Order Desk: 1-888-440-2563\n"
    "Minimum order size FBO: 50 USD"
)

_HISTORY_POLICY_FACTS = (
    "Section 18.01(c) states that this agreement, together with the attached "
    "exhibits, constitutes the entire contract between the parties. Sections "
    "19, 20 and 21 govern termination, assignment and dispute resolution."
)

# The earlier-turn assistant answer the reproduced failure actually copied
# prose from - "user:"/"assistant:" line prefixes, mirroring how
# ``app.orchestrator.chat_orchestrator`` reads session history text.
_HISTORY_WITH_POLICY_FACTS = (
    "user: Is this the whole contract or are there other documents?\n"
    f"assistant: {_HISTORY_POLICY_FACTS}"
)


def _directory_document() -> RetrievedDocument:
    return RetrievedDocument(
        id="sponsoring-098-north-america",
        title="Global Sponsoring Directory",
        content=_DIRECTORY_RECORD,
        source="s3://directory/global-sponsoring.pdf",
        country="GLOBAL",
        metadata={"document_type": "international_sponsoring_directory", "access_scope": "global"},
    )


def _policy_document(content: str = _HISTORY_POLICY_FACTS) -> RetrievedDocument:
    return RetrievedDocument(
        id="us-policy-18",
        title="US-EN-Company-Policy.pdf",
        content=content,
        source="s3://policy/US-EN-Company-Policy.pdf",
        country="US",
        metadata={"document_type": "policy"},
    )


def _context(
    answer: str, documents: list[RetrievedDocument], history: str = ""
) -> ValidationContext:
    return ValidationContext(
        chat_response=ChatResponse(
            answer=answer,
            citations=[],
            suggestions=[],
            cards=[],
            confidence=0.9,
            metadata={},
            correlation_id="test-correlation",
        ),
        correlation_id="test-correlation",
        country="US",
        language="en",
        role="fbo",
        retrieval_result=RetrievalResult(documents=documents, citations=[], confidence=0.6),
        conversation_history=history,
    )


def test_blocks_policy_facts_carried_over_from_history_when_only_a_directory_record_was_retrieved() -> None:
    answer = (
        "This is the whole contract. Section 18.01(c) states that this agreement, "
        "together with the attached exhibits, constitutes the entire contract "
        "between the parties. Sections 19, 20 and 21 govern termination, "
        "assignment and dispute resolution."
    )
    result = ValidationResult()

    HistoryGroundingValidator().validate(
        _context(answer, [_directory_document()], history=_HISTORY_WITH_POLICY_FACTS), result
    )

    assert result.has_critical()
    codes = {issue.code for issue in result.issues}
    assert "HISTORY_SOURCED_CLAIM_UNGROUNDED" in codes


def test_same_reproduction_without_history_is_not_flagged() -> None:
    """Turn 0 of a conversation: the identical uncovered sentences must not be
    flagged with no history present at all to have copied them from - the
    first of the two false-positive classes this fix closes."""
    answer = (
        "This is the whole contract. Section 18.01(c) states that this agreement, "
        "together with the attached exhibits, constitutes the entire contract "
        "between the parties. Sections 19, 20 and 21 govern termination, "
        "assignment and dispute resolution."
    )
    result = ValidationResult()

    HistoryGroundingValidator().validate(_context(answer, [_directory_document()]), result)

    assert result.valid
    assert not result.issues


def test_never_produces_a_half_emptied_list_it_only_flags_for_fallback() -> None:
    """The validator never rewrites the answer; a caller that discards it on
    CRITICAL gets a clean fallback, never a partially stripped numbered list
    like the one that shipped live (items 2, 3 and 4 empty)."""
    answer = (
        "This is the entire agreement, and it fully covers every requirement "
        "without needing any additional referenced material, and it includes:\n"
        "1. The main agreement\n"
        "2. Section 19 on termination\n"
        "3. Section 20 on assignment\n"
        "4. Section 21 on dispute resolution"
    )
    original_answer = answer
    history = (
        "user: Is this the whole contract or are there other documents?\n"
        "assistant: This is the entire agreement, and it fully covers every "
        "requirement without needing any additional referenced material, and "
        "it includes the main agreement, section 19 on termination, section "
        "20 on assignment and section 21 on dispute resolution."
    )
    result = ValidationResult()

    HistoryGroundingValidator().validate(
        _context(answer, [_directory_document()], history=history), result
    )

    assert result.has_critical()
    # The validator only ever reports issues; it must never mutate the answer
    # under review into a half-emptied version of itself.
    assert original_answer == answer


def test_positive_control_full_answer_preserved_when_policy_evidence_is_present() -> None:
    """The same question, this time with the real policy section retrieved:
    nothing should be stripped or flagged."""
    answer = (
        "This is the whole contract. Section 18.01(c) states that this agreement, "
        "together with the attached exhibits, constitutes the entire contract "
        "between the parties. Sections 19, 20 and 21 govern termination, "
        "assignment and dispute resolution."
    )
    result = ValidationResult()

    HistoryGroundingValidator().validate(
        _context(answer, [_directory_document(), _policy_document()]), result
    )

    assert result.valid
    assert not result.issues


def test_followup_turn_still_answers_from_evidence_with_history_present() -> None:
    """"Tell me more" must keep resolving against evidence retrieved this turn."""
    answer = "Sections 19, 20 and 21 govern termination, assignment and dispute resolution."
    result = ValidationResult()

    HistoryGroundingValidator().validate(
        _context(answer, [_policy_document(), _directory_document()]), result
    )

    assert result.valid


def test_directory_only_answer_to_a_directory_question_is_untouched() -> None:
    """A directory-only turn answering a directory question is legitimately
    grounded in the directory record's own fields and must not be flagged."""
    answer = "The order desk number is 1-888-440-2563, and the minimum FBO order is 50 USD."
    result = ValidationResult()

    HistoryGroundingValidator().validate(_context(answer, [_directory_document()]), result)

    assert result.valid


def test_generic_service_boilerplate_beside_a_directory_supplement_is_not_flagged() -> None:
    """A short, generic customer-care referral is not a factual claim about
    anything the directory record states or omits, and must not be confused
    for one merely because it shares little vocabulary with the record.

    Reproduces the false positive found in tests/unit/test_demo_support_contact_wiring.py:
    a "please contact customer care" style answer, with a directory-sourced
    phone number appended, must survive untouched.
    """
    answer = (
        "You are welcome to place an order directly. Please contact customer "
        "care for further help. Telephone Office: 1-888-440-2563."
    )
    result = ValidationResult()

    HistoryGroundingValidator().validate(_context(answer, [_directory_document()]), result)

    assert result.valid
    assert not result.issues


def test_non_policy_turn_without_retrieval_is_untouched() -> None:
    """A greeting or capability answer with no retrieval result must not be
    dragged through the groundedness check."""
    answer = "Hi! I can help with questions about your Forever Living business."
    result = ValidationResult()

    context = ValidationContext(
        chat_response=ChatResponse(
            answer=answer,
            citations=[],
            suggestions=[],
            cards=[],
            confidence=0.9,
            metadata={},
            correlation_id="test-correlation",
        ),
        correlation_id="test-correlation",
        country="US",
        language="en",
        role="fbo",
        retrieval_result=None,
    )

    HistoryGroundingValidator().validate(context, result)

    assert result.valid
    assert not result.issues


def test_empty_answer_is_untouched() -> None:
    result = ValidationResult()

    HistoryGroundingValidator().validate(_context("", [_directory_document()]), result)

    assert result.valid
    assert not result.issues


def test_followup_offer_and_question_not_covered_by_history_are_not_flagged() -> None:
    """Reproduces the "Tell me more" turn of the live failure: a clarifying
    question and a forward-looking offer, neither of which history itself
    states, must not be flagged even though history is present and neither
    sentence is covered by this turn's thin directory-only evidence."""
    answer = (
        "What specific information would you like to know more about? "
        "Please let me know what would be most helpful, and I will provide "
        "the details from our approved resources."
    )
    result = ValidationResult()

    HistoryGroundingValidator().validate(
        _context(answer, [_directory_document()], history=_HISTORY_WITH_POLICY_FACTS), result
    )

    assert result.valid
    assert not result.issues


def test_question_sentence_covered_by_history_is_still_not_flagged() -> None:
    """A question asserts no fact, so it is never flagged even when its own
    vocabulary happens to be covered by conversation history."""
    history = (
        "user: How do I sponsor someone in Belgium?\n"
        "assistant: Would you like to know more about qualification "
        "requirements or the application process for Belgium sponsoring?"
    )
    answer = (
        "Would you like to know more about qualification requirements or the "
        "application process for Belgium sponsoring?"
    )
    result = ValidationResult()

    HistoryGroundingValidator().validate(
        _context(answer, [_directory_document()], history=history), result
    )

    assert result.valid
    assert not result.issues


def test_spanish_question_sentence_covered_by_history_is_not_flagged() -> None:
    """The interrogative skip is language-agnostic: a Spanish "¿...?" sentence
    covered by history is still not flagged."""
    history = (
        "user: ¿Cómo puedo patrocinar a alguien en Bélgica?\n"
        "assistant: ¿Le gustaría conocer los requisitos de "
        "calificación o el proceso de solicitud para Bélgica?"
    )
    answer = (
        "¿Le gustaría conocer los requisitos de calificación o "
        "el proceso de solicitud para Bélgica?"
    )
    result = ValidationResult()

    HistoryGroundingValidator().validate(
        _context(answer, [_directory_document()], history=history), result
    )

    assert result.valid
    assert not result.issues


def test_non_english_history_sourced_claim_is_flagged() -> None:
    """The history-sourced-claim check is language-agnostic: a Spanish factual
    sentence copied from an earlier assistant turn is flagged the same way
    the English reproduction is."""
    history_facts = (
        "La sección 18.01(c) establece que este acuerdo, junto con los "
        "anexos adjuntos, constituye el contrato completo entre las partes. "
        "Las secciones 19, 20 y 21 rigen la terminación, la cesión "
        "y la resolución de disputas."
    )
    history = (
        "user: ¿Es este todo el contrato o hay otros documentos?\n"
        f"assistant: {history_facts}"
    )
    result = ValidationResult()

    HistoryGroundingValidator().validate(
        _context(history_facts, [_directory_document()], history=history), result
    )

    assert result.has_critical()
    codes = {issue.code for issue in result.issues}
    assert "HISTORY_SOURCED_CLAIM_UNGROUNDED" in codes
